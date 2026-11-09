"""#919 H2 · Decisiones vigentes: de unas decisiones candidatas, las que valen HOY.

Lógica pura (sin red ni base), para probarla sola. Recibe las memorias candidatas y `leer(id)`,
que devuelve una memoria con su metadata o None. Sigue cada cadena «superada por» hasta la vigente
(A→B→C devuelve C, «sustituye a A, B»), registra los ciclos como error sin colgarse, quita las
caducadas (valid_until pasado) y, con incluir_superadas, deja también las superadas con su motivo.
EcoDB no sabe nada de FarOS: esto solo mira memorias.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

MAX_SALTOS = 20


def _meta(m: dict) -> dict:
    return m.get("metadata") or {}


def _caducada(m: dict, hoy: date) -> bool:
    vu = _meta(m).get("valid_until")
    if not vu:
        return False
    try:
        return date.fromisoformat(str(vu)[:10]) < hoy
    except ValueError:
        return False


def _fila(m: dict, sustituye: list[str]) -> dict:
    fila = {
        "id": str(m["id"]),
        "fecha": str(m.get("created_at") or "")[:10],
        "tipo": m.get("type"),
        "agente": m.get("agent_identifier"),
        "decidido_por": _meta(m).get("decidido_por"),
        "linea": " ".join(str(m.get("content") or "").split())[:200],
        "fuente": "EcoDB",
    }
    if sustituye:
        fila["sustituye_a"] = sustituye
    vu = _meta(m).get("valid_until")
    if vu:
        fila["valid_until"] = str(vu)[:10]
    return fila


def vigentes(candidatas: list[dict], leer: Callable[[str], Optional[dict]], hoy: Optional[date] = None,
             incluir_superadas: bool = False, limit: int = 10) -> dict:
    """Devuelve {"vigentes": [...], "superadas": [...], "errores": [...]} en el orden de las candidatas."""
    hoy = hoy or date.today()
    vistas: dict[str, dict] = {}
    salida, superadas, errores, ya = [], [], [], set()

    def cargar(mid: str) -> Optional[dict]:
        if mid not in vistas:
            m = leer(mid)
            if m is not None:
                vistas[mid] = m
        return vistas.get(mid)

    for c in candidatas:
        vistas.setdefault(str(c["id"]), c)
        actual, camino = vistas[str(c["id"])], []
        while _meta(actual).get("superseded_by"):
            if len(camino) >= MAX_SALTOS or str(actual["id"]) in camino:
                errores.append({"ciclo": camino + [str(actual["id"])]})
                actual = None
                break
            siguiente = cargar(str(_meta(actual)["superseded_by"]))
            if siguiente is None:   # la sustituta no se puede leer (borrada o ajena): se avisa
                errores.append({"sustituta_no_legible": str(_meta(actual)["superseded_by"]),
                                "de": str(actual["id"])})
                break
            camino.append(str(actual["id"]))
            actual = siguiente
        if actual is None:
            continue
        if incluir_superadas and camino:
            original = vistas[str(c["id"])]
            superadas.append({**_fila(original, []), "superada_por": str(_meta(original)["superseded_by"]),
                              "supersede_kind": _meta(original).get("supersede_kind", "total"),
                              "motivo": _meta(original).get("supersede_reason")})
        if str(actual["id"]) in ya or _caducada(actual, hoy):
            continue
        ya.add(str(actual["id"]))
        salida.append(_fila(actual, camino))
        if len(salida) >= limit:
            break
    resultado = {"vigentes": salida, "errores": errores}
    if incluir_superadas:
        resultado["superadas"] = superadas
    return resultado
