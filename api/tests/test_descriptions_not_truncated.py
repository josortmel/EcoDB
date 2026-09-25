"""#360: agent-facing descriptions must not be truncated.

A pre-release scrub removed the contents of parentheticals, leaving text like
"filtrar por creador (." or ". Audit log obligatorio." — the agent reads less
than was meant and nothing flags it. This test scans the text agents actually
see: `description=` of Field/Query/Path/Body in api/, docstrings of @mcp.tool
functions in mcp/server.py and of @tool functions in ecodb-langchain, and
docstrings of FastAPI route functions (@router.get/post/...), which FastAPI
publishes as the OpenAPI operation description.

Static (AST) check — no DB, no running API.
"""
import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

TRUNCATION_PATTERNS = {
    "dangling '(.'": re.compile(r"\(\.(?=\s|$|\))"),
    "open '(' at end of line": re.compile(r"\(\s*$"),
    "fragment '(.<digits>'": re.compile(r"\(\.\d"),
    "starts with '. '": re.compile(r"^\.\s"),
    "word then orphan ' .'": re.compile(r"\w\s+\.(\s|$)"),
    "'( ' followed by dash": re.compile(r"\(\s+[—-]"),
}
_PARAM_CALLS = {"Field", "Query", "Path", "Body", "Header", "Form"}
_DOC_DECORATORS = {"mcp.tool", "tool"} | {
    f"{obj}.{verb}" for obj in ("router", "app") for verb in ("get", "post", "put", "patch", "delete", "head")}


def truncations(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        stripped = line.strip()
        for name, rx in TRUNCATION_PATTERNS.items():
            if rx.search(stripped):
                found.append(f"{name}: {stripped!r}")
    return found


def _decorator_name(dec: ast.expr) -> str:
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Attribute):
        return f"{getattr(target.value, 'id', '')}.{target.attr}"
    return getattr(target, "id", "")


def agent_facing_texts(source: str, filename: str = "<src>") -> list[tuple[str, str]]:
    """(location, text) for every description= literal and every tool docstring."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in _PARAM_CALLS:
            for kw in node.keywords:
                if kw.arg == "description" and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, str):
                    out.append((f"{filename}:{kw.value.lineno}", kw.value.value))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(_decorator_name(d) in _DOC_DECORATORS for d in node.decorator_list):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    out.append((f"{filename}:{node.lineno} {node.name}()", doc))
    return out


def _scanned_files() -> list[Path]:
    files = sorted((REPO / "api").glob("*.py"))
    files.append(REPO / "mcp" / "server.py")
    files += sorted((REPO / "ecodb-langchain" / "src" / "ecodb_langchain").glob("*.py"))
    return files


def test_detector_flags_fabricated_truncation():
    fabricated = '''
from fastapi import Query
def f(user: int = Query(None, description="Filtrar por creador (."),
      scope: bool = Query(False, description=". Audit log obligatorio.")): ...
'''
    texts = agent_facing_texts(fabricated)
    assert len(texts) == 2
    assert all(truncations(t) for _, t in texts)


def test_detector_accepts_complete_parentheticals():
    ok = '''
from fastapi import Query
def f(t: float = Query(0.7, description="Score minimo (0-1). Default 0.7 (ver .env)."),
      e: str = Query(None, description="Extensiones (.png/.jpg) soportadas.")): ...
'''
    assert not any(truncations(t) for _, t in agent_facing_texts(ok))


def test_repo_agent_facing_descriptions_not_truncated():
    problems = []
    for path in _scanned_files():
        rel = path.relative_to(REPO).as_posix()
        for loc, text in agent_facing_texts(path.read_text(encoding="utf-8"), rel):
            problems += [f"{loc} — {p}" for p in truncations(text)]
    assert not problems, "Truncated agent-facing descriptions:\n" + "\n".join(problems)
