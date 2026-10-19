"""#605: classify_with_llm devolvía el mismo None callado por motivos distintos (sin proveedor, el modelo
dice «other», el proveedor falla…). El 16-oct una medida leyó «None en 20 de 20» como un fallo, y era el
proceso sin proveedor. Ahora cada salida cuenta su motivo (CLASSIFY_LLM_OUTCOMES) y lo dice en el log
ecodb.perf, sin cambiar lo que devuelve.
"""

import asyncio
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import classifier  # noqa: E402
import llm_provider  # noqa: E402


class _FakeProvider:
    def __init__(self, reply):
        self.reply = reply

    async def generate(self, prompt, max_tokens=60, temperature=0.1):
        return self.reply


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    classifier.CLASSIFY_LLM_OUTCOMES.clear()
    yield
    classifier.CLASSIFY_LLM_OUTCOMES.clear()


def _classify(monkeypatch, provider):
    monkeypatch.setattr(llm_provider, "_provider", provider)
    return asyncio.run(classifier.classify_with_llm("Decidimos pasar la base a Postgres 16."))


@pytest.mark.parametrize("provider, outcome", [
    (None, "no_provider"),                                   # proceso sin el lifespan de main.py, o el LLM apagado
    (_FakeProvider(None), "empty"),                          # el proveedor falló (llm_provider ya avisa) o no dijo nada
    (_FakeProvider('{"type": "other"}'), "other"),           # respuesta legítima: no es de ningún tipo
    (_FakeProvider('{"type": "poema"}'), "unknown_type"),    # un tipo que no existe
    (_FakeProvider("no es json"), "bad_json"),
])
def test_cada_none_dice_su_motivo(monkeypatch, provider, outcome):
    assert _classify(monkeypatch, provider) is None
    assert dict(classifier.CLASSIFY_LLM_OUTCOMES) == {outcome: 1}


def test_lo_clasificado_tambien_se_cuenta(monkeypatch):
    out = _classify(monkeypatch, _FakeProvider('{"type": "decision", "confidence": 0.8}'))
    assert out["template_type"] == "decision"
    assert dict(classifier.CLASSIFY_LLM_OUTCOMES) == {"classified": 1}


def test_el_motivo_sale_en_el_log_de_perf(monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger="ecodb.perf"):
        _classify(monkeypatch, None)
    assert any("classify_with_llm outcome=no_provider" in r.getMessage() for r in caplog.records)
