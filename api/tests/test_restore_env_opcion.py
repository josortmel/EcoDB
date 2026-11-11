"""#1083: restore.sh --recover --env=production. Solo se prueba lo que no necesita Docker: la opción
se acepta con --recover, se rechaza con otro valor o sin --recover. La recuperación entera la mide la
repetición del experimento (#913)."""
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "restore.sh"
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="sin bash")


def _run(*args):
    return subprocess.run([BASH, str(SCRIPT), "no-existe.sql.gz", *args], capture_output=True, text=True)


def test_env_production_con_recover_pasa_el_analisis_de_argumentos():
    r = _run("--recover", "--env=production")
    assert r.returncode == 1 and "dump file not found" in r.stderr   # llegó hasta mirar el fichero


def test_env_con_un_valor_raro_se_rechaza():
    r = _run("--recover", "--env=produccion")
    assert r.returncode == 1 and "solo admite development o production" in r.stderr


def test_env_sin_recover_se_rechaza():
    r = _run("--env=production")
    assert r.returncode == 1 and "solo tiene sentido con --recover" in r.stderr
