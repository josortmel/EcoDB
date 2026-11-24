"""#1316 (vigilancia del stack, 18-nov): GHSA-wqgw-9xfh-qf2g (abrir un TIFF de 144 KB se come 1,6 GiB) y
GHSA-xcvg-w56q-r89m (guardar un TIFF con libtiff). El arreglo es Pillow 13, pero en la api no se puede
instalar: docling-slim 2.120.3 pide pillow<13 (lo admite desde la 2.142.0). Mitigación, como con FlashPix
(#792): mientras Pillow sea < 13, pillow_guard quita TIFF de lo que Pillow abre y guarda. En EcoDB no se ha
guardado nunca un TIFF (0 de 178 memorias con fichero y 0 de 246 documentos, 24-nov); las imágenes de la
búsqueda visual las decodifica embeddings, que sí va en Pillow 13."""

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

PIL_MAJOR = int(__import__("PIL").__version__.split(".")[0])
pytestmark = pytest.mark.skipif(PIL_MAJOR >= 13, reason="Pillow 13 ya trae el arreglo: TIFF se queda")


@pytest.mark.parametrize("entry", ["main", "worker", "cell_worker"])
def test_cada_entrada_quita_tiff_al_arrancar(entry):
    code = (
        f"import {entry}; from PIL import Image; Image.init(); "
        "print('TIFF' in Image.OPEN, 'TIFF' in Image.SAVE, 'TIFF' in Image.ID)"
    )
    env = {**os.environ, "DATABASE_URL": os.environ.get("DATABASE_URL", "postgresql://x@127.0.0.1:1/x")}
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=API_DIR, capture_output=True, text=True, timeout=120, env=env
    )  # importing never connects
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.split()[-3:] == ["False", "False", "False"]


def test_un_tiff_no_se_abre_ni_se_guarda():
    from PIL import Image, UnidentifiedImageError

    # El TIFF se fabrica en un proceso aparte, donde Pillow todavía lo sabe escribir.
    hecho = subprocess.run(
        [
            sys.executable,
            "-c",
            "import io,sys; from PIL import Image; b=io.BytesIO(); "
            "Image.new('RGB',(4,4)).save(b,format='TIFF'); sys.stdout.buffer.write(b.getvalue())",
        ],
        capture_output=True,
        timeout=60,
    )
    assert hecho.returncode == 0 and hecho.stdout[:2] in (b"II", b"MM")

    import pillow_guard  # noqa: F401

    Image.init()
    with pytest.raises(UnidentifiedImageError):
        Image.open(io.BytesIO(hecho.stdout))
    with pytest.raises((KeyError, ValueError, OSError)):
        Image.new("RGB", (4, 4)).save(io.BytesIO(), format="TIFF")
