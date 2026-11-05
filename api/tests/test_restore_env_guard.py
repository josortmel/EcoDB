"""#968: cada variable de docker-compose tiene dueño en una recuperación desde cero.

Un ${NUEVO} sin clasificar sería un secreto que restore.sh no rehace, y se notaría el día del
desastre. Por eso falla aquí y no entonces.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LISTAS = ("GENERATED_ENV", "EXTERNAL_ENV", "CONFIG_ENV")


def clasificadas(script: str) -> set[str]:
    nombres: set[str] = set()
    for lista in LISTAS:
        nombres |= set(re.search(rf'^{lista}="([^"]*)"', script, re.M).group(1).split())
    return nombres


def sin_clasificar(compose: str, script: str) -> set[str]:
    return set(re.findall(r"\$\{([A-Z0-9_]+)", compose)) - clasificadas(script)


def _script() -> str:
    return (REPO / "scripts" / "restore.sh").read_text(encoding="utf-8")


def test_todo_lo_de_compose_esta_clasificado():
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert sin_clasificar(compose, _script()) == set()


def test_un_nombre_nuevo_sin_clasificar_hace_fallar_la_guarda():
    assert sin_clasificar("FOO: ${NUEVO:?falta}", _script()) == {"NUEVO"}


def test_env_example_trae_lo_generado():
    ejemplo = (REPO / ".env.example").read_text(encoding="utf-8")
    generadas = re.search(r'^GENERATED_ENV="([^"]*)"', _script(), re.M).group(1).split()
    assert [n for n in generadas if not re.search(rf"^{n}=", ejemplo, re.M)] == []
