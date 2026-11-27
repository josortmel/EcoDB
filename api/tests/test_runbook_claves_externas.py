"""#1423: la tabla «What to keep» del runbook nombra cada clave externa que restore.sh no puede regenerar.

restore.sh lista en EXTERNAL_ENV las claves que hay que volver a pegar después de una recuperación total.
Si una de ellas no está en la fila de claves externas de la tabla, quien sigue el runbook no la guarda
antes de que el disco muera (lo vio Hilo con TELEGRAM_BOT_TOKEN al verificar #1397)."""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "restore.sh"
RUNBOOK = RAIZ / "docs" / "EcoDB_runbook_backup.md"


def _claves_externas_del_script():
    m = re.search(r'^EXTERNAL_ENV="([^"]*)"', SCRIPT.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, "restore.sh ya no define EXTERNAL_ENV"
    return m.group(1).split()


def _fila_de_claves_externas():
    filas = [
        linea
        for linea in RUNBOOK.read_text(encoding="utf-8").splitlines()
        if linea.startswith("|") and "external providers" in linea
    ]
    assert len(filas) == 1, "no encuentro una sola fila de claves externas en «What to keep»"
    return filas[0]


def test_cada_clave_externa_de_restore_sh_esta_en_la_tabla_que_guardar():
    fila = _fila_de_claves_externas()
    faltan = [k for k in _claves_externas_del_script() if f"`{k}`" not in fila]
    assert not faltan, f"faltan en la tabla «What to keep»: {faltan}"
