"""Contract test (#369): every query param the clients send to GET /memories/recent
must be one the API endpoint actually reads. FastAPI silently ignores unknown
query params, so a name mismatch (MCP sent `tags`, API reads `tag`) disables the
filter without any error.

Static (AST) check — no DB, no running API, no imports of the modules.
"""
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API_FILE = REPO / "api" / "memories.py"
CLIENT_FILES = {
    "mcp": (REPO / "mcp" / "server.py", "search_recent"),
    "ecodb-langchain": (REPO / "ecodb-langchain" / "src" / "ecodb_langchain" / "client.py", "search_recent"),
}


def _find_func(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


def api_query_names() -> set[str]:
    """Wire names of list_recent's Query params (alias wins over the Python name)."""
    func = _find_func(ast.parse(API_FILE.read_text(encoding="utf-8")), "list_recent")
    args = func.args.args
    defaults = [None] * (len(args) - len(func.args.defaults)) + list(func.args.defaults)
    names = set()
    for arg, default in zip(args, defaults):
        if isinstance(default, ast.Call) and getattr(default.func, "id", None) == "Query":
            alias = next((kw.value.value for kw in default.keywords if kw.arg == "alias"), None)
            names.add(alias or arg.arg)
    return names


def sent_param_names(path: Path, func_name: str) -> set[str]:
    """Keys the client puts in `params` (dict literal + params["x"] = ...)."""
    func = _find_func(ast.parse(path.read_text(encoding="utf-8")), func_name)
    names = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "params" and isinstance(node.value, ast.Dict):
                    names |= {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
                if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                        and target.value.id == "params" and isinstance(target.slice, ast.Constant)):
                    names.add(target.slice.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == "params" and isinstance(node.value, ast.Dict):
            names |= {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    return names


def test_api_reads_tag():
    assert "tag" in api_query_names()


def test_mcp_search_recent_params_are_read_by_api():
    path, func = CLIENT_FILES["mcp"]
    sent = sent_param_names(path, func)
    assert "tag" in sent, f"MCP search_recent does not send the tag filter: {sent}"
    assert sent <= api_query_names(), f"MCP sends params the API ignores: {sent - api_query_names()}"


def test_langchain_search_recent_params_are_read_by_api():
    path, func = CLIENT_FILES["ecodb-langchain"]
    sent = sent_param_names(path, func)
    assert "tag" in sent, f"SDK search_recent does not send the tag filter: {sent}"
    assert sent <= api_query_names(), f"SDK sends params the API ignores: {sent - api_query_names()}"
