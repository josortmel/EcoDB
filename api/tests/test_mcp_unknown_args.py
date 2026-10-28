"""#492 (Prima, 13-oct; el mismo fallo que el #339 de FarOS): una tool del MCP que recibe un
argumento que NO declara tiene que fallar nombrándolo, no descartarlo en silencio.

FastMCP valida los argumentos con ArgModelBase, que ignoraba lo que sobra: read_memory(memory_id=…,
campo_que_no_existe=…) devolvía la memoria normal, y un filtro mal escrito en search («agent» en
vez de «agent_identifier») corría la búsqueda SIN filtro sin que nadie se enterara.
Offline: httpx con respx, sin API ni base.
"""
import asyncio
import importlib.util
from pathlib import Path

import pytest
import respx

SERVER = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
API = "http://localhost:8080"
MEM = "ea1fe3d3-b57c-4178-a3cb-407c950e242e"


@pytest.fixture
def mod(monkeypatch):
    monkeypatch.setenv("ECODB_API_URL", API)
    monkeypatch.setenv("ECODB_API_KEY", "ecodb_test")
    spec = importlib.util.spec_from_file_location("ecodb_mcp_server_492", SERVER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m._jwt = None
    return m


@pytest.fixture
def api():
    with respx.mock(base_url=API, assert_all_called=False) as r:
        r.post("/auth/token").respond(200, json={"access_token": "t", "expires_in": 3600})
        r.get(f"/memories/{MEM}").respond(200, json={"id": MEM, "content": "x"})
        r.post("/search").respond(200, json={"results": []})
        yield r


def _calls(api):
    return [c.request.url.path for c in api.calls if not c.request.url.path.startswith("/auth")]


@pytest.mark.parametrize("tool,args,bad", [
    ("read_memory", {"memory_id": MEM, "campo_que_no_existe": "prueba #492"}, "campo_que_no_existe"),
    ("search", {"query_text": "la pluma", "agent": "Hilo"}, "agent"),
])
def test_un_argumento_no_declarado_falla_y_lo_nombra(mod, api, tool, args, bad):
    with pytest.raises(Exception) as e:
        asyncio.run(mod.mcp.call_tool(tool, args))
    assert bad in str(e.value)
    assert _calls(api) == [], "con un argumento desconocido no debe salir ninguna petición a la API"


def test_los_argumentos_declarados_siguen_pasando(mod, api):
    asyncio.run(mod.mcp.call_tool("read_memory", {"memory_id": MEM}))
    assert _calls(api) == [f"/memories/{MEM}"]


def test_todas_las_tools_prohiben_argumentos_desconocidos(mod):
    """Si una versión de mcp mueve ArgModelBase, server.py se degrada al comportamiento viejo
    (solo avisa por stderr). Este test lo caza."""
    tools = mod.mcp._tool_manager.list_tools()
    assert len(tools) >= 30
    sueltas = [t.name for t in tools if t.fn_metadata.arg_model.model_config.get("extra") != "forbid"]
    assert sueltas == []
