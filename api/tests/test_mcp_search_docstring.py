"""#360 (second vector) + #365: the MCP `search` docstring is the agent's only
manual. Clients truncate long tool descriptions (~2000 chars), so everything
after the cut (cluster_mode, response fields) was invisible. It must stay
short and must name every parameter. Also: include_dormant must be exposed
and passed through to POST /search. Static (AST) check.
"""
import ast
from pathlib import Path

SERVER = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
MAX_DOC_CHARS = 2000


def _search_func() -> ast.FunctionDef:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "search")


def test_search_docstring_fits_client_limit():
    doc = ast.get_docstring(_search_func())
    assert len(doc) < MAX_DOC_CHARS, f"search docstring is {len(doc)} chars"


def test_search_docstring_names_every_param():
    func = _search_func()
    doc = ast.get_docstring(func)
    missing = [a.arg for a in func.args.args if a.arg not in doc]
    assert not missing, f"params missing from docstring: {missing}"


def test_search_docstring_documents_response_warnings():
    assert "warnings" in ast.get_docstring(_search_func())


def test_search_exposes_and_forwards_include_dormant():
    func = _search_func()
    assert "include_dormant" in [a.arg for a in func.args.args]
    forwarded = {
        node.targets[0].slice.value
        for node in ast.walk(func)
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Subscript)
        and getattr(node.targets[0].value, "id", None) == "payload"
        and isinstance(node.targets[0].slice, ast.Constant)
    }
    assert "include_dormant" in forwarded


def test_search_always_forwards_include_documents():
    """C8b: API default is True, so False is only honoured if it is always sent."""
    func = _search_func()
    top_level_keys = set()
    for stmt in func.body:  # direct statements, not nested under an `if`
        if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Subscript) \
                and getattr(stmt.targets[0].value, "id", None) == "payload":
            top_level_keys.add(stmt.targets[0].slice.value)
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and isinstance(stmt.value, ast.Dict) \
                and getattr(stmt.targets[0] if isinstance(stmt, ast.Assign) else stmt.target, "id", None) == "payload":
            top_level_keys |= {k.value for k in stmt.value.keys if isinstance(k, ast.Constant)}
    assert "include_documents" in top_level_keys


def test_search_docstring_says_none_still_returns_related_clusters():
    doc = ast.get_docstring(_search_func())
    line = next(l for l in doc.splitlines() if l.strip().startswith("cluster_mode:"))
    assert "3" in line and "related_clusters" in line
