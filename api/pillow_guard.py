"""#792/#811: GHSA-5x8w-8jj5-q52h (critical) — Pillow <= 12.3.0 overflows decoding the JPEG inside a
FlashPix and allows code execution; the fix is Pillow 13 (major). olefile is installed, so FPX is
registered. Everything is loaded once (init) and FPX is removed: init() doesn't load plugins again.
Imported FIRST by every entry point (main, worker, cell_worker) and by parsers, so no image is ever
opened while FPX is still registered (#811: before, only importing parsers removed it).

#1316/#1437: the two TIFF advisories (GHSA-wqgw-9xfh-qf2g, GHSA-xcvg-w56q-r89m) are fixed in Pillow 13,
which the api runs since 1.4.1 (docling 2.142.1 allows it). TIFF was removed here while the api was on
Pillow < 13; test_pillow_13.py now fails if the api ever goes back below 13."""


def remove_flashpix() -> None:
    try:
        from PIL import Image
    except ImportError:
        return
    Image.init()
    Image.OPEN.pop("FPX", None)
    if "FPX" in Image.ID:
        Image.ID.remove("FPX")


remove_flashpix()
