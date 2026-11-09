"""#919 H2: la lógica de decisiones vigentes, sin red ni base."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vigentes import vigentes  # noqa: E402

HOY = date(2026, 11, 9)


def _m(mid, **meta):
    return {"id": mid, "type": "decision", "content": f"decisión {mid}", "created_at": "2026-11-01T10:00:00",
            "agent_identifier": "Hilo", "metadata": meta}


def _base(*mems):
    d = {m["id"]: m for m in mems}
    return d, (lambda mid: d.get(mid))


def test_cadena_a_b_c_devuelve_c_y_dice_a_quien_sustituye():
    d, leer = _base(_m("A", superseded_by="B"), _m("B", superseded_by="C"), _m("C"))
    r = vigentes([d["A"]], leer, HOY)
    assert [f["id"] for f in r["vigentes"]] == ["C"]
    assert r["vigentes"][0]["sustituye_a"] == ["A", "B"]


def test_un_ciclo_se_registra_y_no_cuelga():
    d, leer = _base(_m("A", superseded_by="B"), _m("B", superseded_by="A"))
    r = vigentes([d["A"]], leer, HOY)
    assert r["vigentes"] == []
    # Se detecta al repetirse una memoria, no al agotar el tope de saltos.
    assert r["errores"] == [{"ciclo": ["A", "B", "A"]}]


def test_una_caducada_no_sale():
    d, leer = _base(_m("A", valid_until="2026-11-08"), _m("B", valid_until="2026-11-09"))
    r = vigentes([d["A"], d["B"]], leer, HOY)
    assert [f["id"] for f in r["vigentes"]] == ["B"]   # la de hoy aún vale


def test_la_superada_solo_sale_con_incluir_superadas():
    d, leer = _base(_m("A", superseded_by="B", supersede_reason="cambió"), _m("B"))
    sin = vigentes([d["A"]], leer, HOY)
    assert "superadas" not in sin and [f["id"] for f in sin["vigentes"]] == ["B"]
    con = vigentes([d["A"]], leer, HOY, incluir_superadas=True)
    assert con["superadas"][0]["id"] == "A" and con["superadas"][0]["superada_por"] == "B"
    assert con["superadas"][0]["motivo"] == "cambió"


def test_dos_candidatas_que_llevan_a_la_misma_vigente_salen_una_vez():
    d, leer = _base(_m("A", superseded_by="C"), _m("B", superseded_by="C"), _m("C"))
    r = vigentes([d["A"], d["B"], d["C"]], leer, HOY)
    assert [f["id"] for f in r["vigentes"]] == ["C"]


def test_sustituta_ilegible_se_avisa_y_se_queda_la_que_hay():
    d, leer = _base(_m("A", superseded_by="X"))
    r = vigentes([d["A"]], leer, HOY)
    assert [f["id"] for f in r["vigentes"]] == ["A"]
    assert r["errores"] == [{"sustituta_no_legible": "X", "de": "A"}]


def test_limit_corta():
    mems = [_m(str(i)) for i in range(5)]
    d, leer = _base(*mems)
    assert len(vigentes(mems, leer, HOY, limit=2)["vigentes"]) == 2


def test_decidido_por_y_valid_until_viajan_en_la_fila():
    d, leer = _base(_m("A", decidido_por={"tipo": "humano", "quien": "Pepe"}, valid_until="2026-12-31"))
    f = vigentes([d["A"]], leer, HOY)["vigentes"][0]
    assert f["decidido_por"] == {"tipo": "humano", "quien": "Pepe"} and f["valid_until"] == "2026-12-31"
    assert f["fuente"] == "EcoDB"


# ---- la herramienta del MCP, con la API simulada (y sin FarOS) ----

import os  # noqa: E402

os.environ.setdefault("ECODB_API_URL", "http://localhost:8080")
os.environ.setdefault("ECODB_API_KEY", "clave-de-prueba")
os.environ.setdefault("MCP_TRANSPORT", "stdio")

import server  # noqa: E402


def test_la_herramienta_busca_decisiones_y_acuerdos_y_resuelve_la_cadena(monkeypatch):
    memorias = {"A": _m("A", superseded_by="B"), "B": _m("B", superseded_by="C"), "C": _m("C")}
    llamadas = []

    def falsa(method, path, **kw):
        llamadas.append((method, path, kw.get("json")))
        if path == "/search":
            return {"results": [{"id": "A", "score": 0.9}] if kw["json"]["type"] == "decision" else []}
        return memorias.get(path.rsplit("/", 1)[-1])

    monkeypatch.setattr(server, "_api_call", falsa)
    fn = getattr(server.decisiones_vigentes, "fn", server.decisiones_vigentes)
    r = fn(tema="horario de la tienda", agente="Hilo")
    datos = r.get("data", r)
    assert [f["id"] for f in datos["vigentes"]] == ["C"]
    tipos = sorted(j["type"] for m, p, j in llamadas if p == "/search")
    assert tipos == ["acuerdo", "decision"]
    assert all(j["agent_identifier"] == "Hilo" for m, p, j in llamadas if p == "/search")
