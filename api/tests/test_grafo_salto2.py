"""#1144 (parche del grafo): el salto 2 se puede apagar en todo el servicio (EXPAND_GRAPH_HOP2) o en una
llamada (graph_hop2), para medir encendido y apagado intercalados sobre los mismos datos."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _search(monkeypatch, valor=None):
    if valor is None:
        monkeypatch.delenv("EXPAND_GRAPH_HOP2", raising=False)
    else:
        monkeypatch.setenv("EXPAND_GRAPH_HOP2", valor)
    import search
    return importlib.reload(search)


def test_por_defecto_hace_los_dos_saltos_como_hoy(monkeypatch):
    s = _search(monkeypatch)
    assert s._saltos() == (1, 2)
    assert s.SearchRequest(query_text="hola mundo").graph_hop2 is None


def test_la_variable_lo_apaga_en_todo_el_servicio(monkeypatch):
    for v in ("0", "false", "off", "no", " OFF "):
        assert _search(monkeypatch, v)._saltos() == (1,)
    assert _search(monkeypatch, "1")._saltos() == (1, 2)


def test_la_peticion_manda_sobre_la_variable(monkeypatch):
    apagado = _search(monkeypatch, "0")
    assert apagado._saltos(True) == (1, 2)
    encendido = _search(monkeypatch, "1")
    assert encendido._saltos(False) == (1,)
    _search(monkeypatch)  # deja el módulo como estaba para los demás tests
