"""#1437: the api runs Pillow 13 since 1.4.1 (docling 2.142.1 allows it), and that is what fixes the two TIFF
advisories (GHSA-wqgw-9xfh-qf2g, GHSA-xcvg-w56q-r89m). pillow_guard no longer removes TIFF, so going back
below 13 would reopen them: these tests fail if that happens, in the pin and in what is installed."""

import re
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent


def _major(version: str) -> int:
    return int(version.split(".")[0])


def test_the_constraints_pin_pillow_13_or_later():
    pins = re.findall(r"^pillow==([0-9][^\s]*)$", (API_DIR / "constraints.txt").read_text(encoding="utf-8"), re.M)
    assert len(pins) == 1, pins
    assert _major(pins[0]) >= 13, pins[0]


def test_the_installed_pillow_is_13_or_later():
    import PIL

    assert _major(PIL.__version__) >= 13, PIL.__version__


def test_tiff_opens_again_after_the_guard():
    """The guard still removes FlashPix (#792) but no longer TIFF: a TIFF round-trips."""
    import io

    import pillow_guard  # noqa: F401
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="TIFF")
    buf.seek(0)
    assert Image.open(buf).size == (4, 4)
    assert "FPX" not in Image.OPEN
