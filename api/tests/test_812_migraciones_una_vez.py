"""#812: migrations.py ya no repite todas las migraciones en cada arranque de la api.

Antes, 7 semillas con `ON CONFLICT (name) DO UPDATE SET content = ...` reescribían en cada
reinicio el contenido de las plantillas de la célula y deshacían lo cambiado a mano. Ahora
hay un registro (schema_migrations, nombre + sha256 del fichero) y cada migración corre una
vez por versión de su fichero. Corre contra la base de PRUEBAS (conftest), nunca la viva.
"""

import asyncio
import sys
from pathlib import Path

import asyncpg
import pytest

API = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API))
import migrations  # noqa: E402
from conftest import TEST_DB_URL  # noqa: E402

REPO = API.parent
PLANTILLA = "CellAgent Monthly"
MARCA = " [pytest-812 cambiado a mano]"


@pytest.fixture(autouse=True)
def _en_la_raiz(monkeypatch):
    monkeypatch.chdir(REPO)  # las rutas de MIGRATIONS son relativas, como en /app del contenedor


async def _arranque(veces=1):
    pool = await asyncpg.create_pool(dsn=TEST_DB_URL, min_size=1, max_size=1)
    try:
        for _ in range(veces):
            await migrations.run_migrations(pool)
    finally:
        await pool.close()


async def _q(sql, *a, fetch="val"):
    c = await asyncpg.connect(dsn=TEST_DB_URL)
    try:
        return await getattr(c, {"val": "fetchval", "rows": "fetch", "exec": "execute"}[fetch])(sql, *a)
    finally:
        await c.close()


def test_una_plantilla_cambiada_a_mano_sobrevive_a_dos_arranques():
    async def go():
        await _arranque()
        antes = await _q("SELECT content FROM cell_prompt_templates WHERE name=$1", PLANTILLA)
        if antes is None:
            pytest.skip("la base de pruebas no tiene la plantilla")
        # Una config que una semilla SÍ reescribe: seed_higher_prompts_v2.sql pasa el cron semanal de
        # '0 3 * * 0' a '0 3 * * 1'. Puesto a mano en '0 3 * * 0', el runner viejo lo pisaba al arrancar.
        cfg = await _q(
            """SELECT id, schedule_cron FROM cell_task_configs WHERE cell_type='consolidation'
                          AND level='weekly' ORDER BY id LIMIT 1""",
            fetch="rows",
        )
        assert cfg, "la base de pruebas no tiene config semanal de consolidación: la mitad de la config no mediría nada"
        try:
            await _q(
                "UPDATE cell_prompt_templates SET content = content || $2 WHERE name=$1", PLANTILLA, MARCA, fetch="exec"
            )
            if cfg:
                await _q(
                    "UPDATE cell_task_configs SET schedule_cron='0 3 * * 0' WHERE id=$1", cfg[0]["id"], fetch="exec"
                )
            await _arranque(veces=2)
            despues = await _q("SELECT content FROM cell_prompt_templates WHERE name=$1", PLANTILLA)
            cron = await _q("SELECT schedule_cron FROM cell_task_configs WHERE id=$1", cfg[0]["id"]) if cfg else None
            return despues, cron, bool(cfg)
        finally:
            await _q("UPDATE cell_prompt_templates SET content=$2 WHERE name=$1", PLANTILLA, antes, fetch="exec")
            if cfg:
                await _q(
                    "UPDATE cell_task_configs SET schedule_cron=$2 WHERE id=$1",
                    cfg[0]["id"],
                    cfg[0]["schedule_cron"],
                    fetch="exec",
                )

    despues, cron, hay_cfg = asyncio.run(go())
    assert hay_cfg and cron == "0 3 * * 0", "un arranque de la api ha deshecho la config cambiada a mano"
    assert despues.endswith(MARCA), "un arranque de la api ha deshecho la plantilla cambiada a mano"


def test_una_migracion_corre_otra_vez_solo_si_su_fichero_cambia(tmp_path, monkeypatch):
    f = tmp_path / "pytest_812.sql"
    f.write_text("CREATE TABLE IF NOT EXISTS pytest_812 (n int); INSERT INTO pytest_812 VALUES (1);", encoding="utf-8")
    monkeypatch.setattr(migrations, "MIGRATIONS", migrations.MIGRATIONS + [("pytest_812", str(f))])

    async def go():
        await _q("DROP TABLE IF EXISTS pytest_812", fetch="exec")
        await _q("DELETE FROM schema_migrations WHERE name='pytest_812'", fetch="exec") if await _q(
            "SELECT to_regclass('public.schema_migrations') IS NOT NULL"
        ) else None
        try:
            await _arranque(veces=2)
            dos_arranques = await _q("SELECT count(*) FROM pytest_812")
            f.write_text(f.read_text(encoding="utf-8") + "\n-- cambiada", encoding="utf-8")
            await _arranque()
            tras_cambio = await _q("SELECT count(*) FROM pytest_812")
            return dos_arranques, tras_cambio
        finally:
            await _q("DROP TABLE IF EXISTS pytest_812", fetch="exec")
            await _q("DELETE FROM schema_migrations WHERE name='pytest_812'", fetch="exec")

    assert asyncio.run(go()) == (1, 2)


def test_el_baseline_no_tapa_una_migracion_nueva(tmp_path, monkeypatch):
    """Una base ya migrada sin registro: se apuntan las de antes sin correrlas, pero una nueva corre."""
    f = tmp_path / "pytest_812b.sql"
    f.write_text(
        "CREATE TABLE IF NOT EXISTS pytest_812b (n int); INSERT INTO pytest_812b VALUES (1);", encoding="utf-8"
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", migrations.MIGRATIONS + [("pytest_812b", str(f))])

    async def go():
        await _arranque()  # la base de pruebas queda migrada
        await _q("DROP TABLE IF EXISTS schema_migrations", fetch="exec")
        await _q("DROP TABLE IF EXISTS pytest_812b", fetch="exec")
        antes = await _q("SELECT content FROM cell_prompt_templates WHERE name=$1", PLANTILLA)
        try:
            if antes is not None:
                await _q(
                    "UPDATE cell_prompt_templates SET content = content || $2 WHERE name=$1",
                    PLANTILLA,
                    MARCA,
                    fetch="exec",
                )
            await _arranque()
            filas = await _q("SELECT name, baseline FROM schema_migrations", fetch="rows")
            nueva = await _q("SELECT count(*) FROM pytest_812b")
            despues = await _q("SELECT content FROM cell_prompt_templates WHERE name=$1", PLANTILLA)
            return {r["name"]: r["baseline"] for r in filas}, nueva, antes, despues
        finally:
            await _q("DROP TABLE IF EXISTS pytest_812b", fetch="exec")
            await _q("DELETE FROM schema_migrations WHERE name='pytest_812b'", fetch="exec")
            if antes is not None:
                await _q("UPDATE cell_prompt_templates SET content=$2 WHERE name=$1", PLANTILLA, antes, fetch="exec")

    reg, nueva, antes, despues = asyncio.run(go())
    assert all(reg[n] for n in migrations._BEFORE_REGISTRY), reg
    assert reg["pytest_812b"] is False and nueva == 1
    assert antes is None or despues.endswith(MARCA), "el primer arranque con registro ha vuelto a correr las semillas"
