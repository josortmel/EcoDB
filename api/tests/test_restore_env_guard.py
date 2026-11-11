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


def todos_los_compose(repo: Path) -> dict[str, str]:
    """#1083 (D3 de Prima): no solo docker-compose.yml. Los overrides también piden variables
    (docker-compose.alerting.yml dejaba TELEGRAM_* sin dueño)."""
    return {f.name: f.read_text(encoding="utf-8") for f in sorted(repo.glob("docker-compose*.yml"))}


def test_todo_lo_de_compose_esta_clasificado():
    script = _script()
    faltan = {n: sin_clasificar(c, script) for n, c in todos_los_compose(REPO).items()}
    assert {n: v for n, v in faltan.items() if v} == {}
    assert len(faltan) > 1  # recorre los overrides, no solo el principal


def test_un_nombre_nuevo_sin_clasificar_hace_fallar_la_guarda():
    assert sin_clasificar("FOO: ${NUEVO:?falta}", _script()) == {"NUEVO"}


def test_un_nombre_nuevo_en_un_override_tambien_la_hace_fallar(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("A: ${ECODB_API_KEY}", encoding="utf-8")
    (tmp_path / "docker-compose.extra.yml").write_text("B: ${NUEVO_EN_OVERRIDE}", encoding="utf-8")
    script = _script()
    faltan = {n: sin_clasificar(c, script) for n, c in todos_los_compose(tmp_path).items()}
    assert faltan == {"docker-compose.extra.yml": {"NUEVO_EN_OVERRIDE"}, "docker-compose.yml": set()}


def test_el_aviso_de_claves_externas_sale_de_la_lista():
    """#1083: el aviso de qué volver a pegar se escribía a mano y se quedaba atrás."""
    linea = next(l for l in _script().splitlines() if "si las usabas" in l)
    assert "$EXTERNAL_ENV" in linea
    for nombre in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "CELL_LLM_KEY", "TELEGRAM_BOT_TOKEN"):
        assert nombre not in linea


def test_env_example_trae_lo_generado():
    ejemplo = (REPO / ".env.example").read_text(encoding="utf-8")
    generadas = re.search(r'^GENERATED_ENV="([^"]*)"', _script(), re.M).group(1).split()
    assert [n for n in generadas if not re.search(rf"^{n}=", ejemplo, re.M)] == []
