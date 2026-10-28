"""#603 (L48, Prima 16-oct): PUT /clusters/{id}/narrate tenía max_length 5000, y un dueño no podía volver
a narrar un mensual o un trimestral: los que escribe la propia célula son mucho más largos (medido el
28-oct en producción: mensual hasta 13 463 caracteres, trimestral hasta 22 256). Prima tuvo que rehacer
una narrativa por SQL. El tope pasa a 32 000, el mismo que el de las plantillas de la célula.
Offline: el modelo de entrada, sin API ni base."""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clusters import NarrateBody  # noqa: E402


@pytest.mark.parametrize("n", [1, 4_302, 13_463, 22_256, 32_000])
def test_cabe_cualquier_narrativa_que_escribe_la_celula(n):
    assert len(NarrateBody(narrative="x" * n).narrative) == n


@pytest.mark.parametrize("bad", ["", "x" * 32_001])
def test_vacia_o_por_encima_del_tope_se_rechaza(bad):
    with pytest.raises(ValidationError):
        NarrateBody(narrative=bad)
