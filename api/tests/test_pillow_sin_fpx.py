"""#792 (vigilancia del stack, 28-oct): GHSA-5x8w-8jj5-q52h, crítico. Pillow <= 12.3.0 desborda al
decodificar el JPEG de un FlashPix (FPX) y permite ejecutar código; el arreglo es Pillow 13 (mayor).
En la api el decodificador FPX está registrado (olefile instalado) y docling abre los documentos que se
registran en EcoDB, así que un documento malicioso lo alcanzaría. Mitigación: parsers quita FPX al
importarse, y un Image.init() posterior no lo vuelve a cargar."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


import os
import subprocess

import pytest

API_DIR = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("entry", ["main", "worker", "cell_worker"])
def test_cada_entrada_quita_flashpix_al_arrancar_sin_tocar_parsers(entry):
    """#811: each container's entry point removes FPX on its own, in a fresh process, before any
    document reaches parsers (Lienzo's note verifying #792)."""
    code = (f"import {entry}, sys; from PIL import Image; Image.init(); "
            "print('FPX' in Image.OPEN, 'FPX' in Image.ID, 'parsers' in sys.modules)")
    env = {**os.environ, "DATABASE_URL": os.environ.get("DATABASE_URL", "postgresql://x@127.0.0.1:1/x")}
    # Prima, 29-oct: on a Pillow that never registers FPX (her host) this would pass on the old
    # code too and prove nothing. It only means something where FPX is there to remove.
    probe = subprocess.run([sys.executable, "-c", "from PIL import Image; Image.init(); print('FPX' in Image.OPEN)"],
                           capture_output=True, text=True, timeout=60)
    if probe.stdout.strip() != "True":
        pytest.skip("this Pillow doesn't register FlashPix: nothing to remove, nothing to prove")
    out = subprocess.run([sys.executable, "-c", code], cwd=API_DIR, capture_output=True,
                         text=True, timeout=120, env=env)  # importing never connects
    assert out.returncode == 0, out.stderr[-2000:]
    fpx_open, fpx_id, _parsers = out.stdout.split()[-3:]
    assert (fpx_open, fpx_id) == ("False", "False")


def test_al_importar_parsers_flashpix_no_se_decodifica():
    import parsers  # noqa: F401
    from PIL import Image
    Image.init()
    assert "FPX" not in Image.OPEN
    assert "FPX" not in Image.ID
