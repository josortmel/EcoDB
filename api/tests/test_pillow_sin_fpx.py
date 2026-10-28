"""#792 (vigilancia del stack, 28-oct): GHSA-5x8w-8jj5-q52h, crítico. Pillow <= 12.3.0 desborda al
decodificar el JPEG de un FlashPix (FPX) y permite ejecutar código; el arreglo es Pillow 13 (mayor).
En la api el decodificador FPX está registrado (olefile instalado) y docling abre los documentos que se
registran en EcoDB, así que un documento malicioso lo alcanzaría. Mitigación: parsers quita FPX al
importarse, y un Image.init() posterior no lo vuelve a cargar."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_al_importar_parsers_flashpix_no_se_decodifica():
    import parsers  # noqa: F401
    from PIL import Image
    Image.init()
    assert "FPX" not in Image.OPEN
    assert "FPX" not in Image.ID
