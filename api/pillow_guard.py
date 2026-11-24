"""#792/#811: GHSA-5x8w-8jj5-q52h (critical) — Pillow <= 12.3.0 overflows decoding the JPEG inside a
FlashPix and allows code execution; the fix is Pillow 13 (major). olefile is installed, so FPX is
registered. Everything is loaded once (init) and FPX is removed: init() doesn't load plugins again.
Imported FIRST by every entry point (main, worker, cell_worker) and by parsers, so no image is ever
opened while FPX is still registered (#811: before, only importing parsers removed it).

#1316: GHSA-wqgw-9xfh-qf2g (opening a 144 KB TIFF eats 1.6 GiB) and GHSA-xcvg-w56q-r89m (saving a
TIFF with libtiff), also fixed in Pillow 13. The api can't install 13 yet (docling-slim 2.120.3 pins
pillow<13; 2.142.0 allows it), so while Pillow < 13 TIFF is removed from open and save too. EcoDB has
never stored a TIFF (0 on 24-nov); visual-search images are decoded by embeddings, already on 13."""


def remove_flashpix() -> None:
    try:
        from PIL import Image
    except ImportError:
        return
    Image.init()
    Image.OPEN.pop("FPX", None)
    if "FPX" in Image.ID:
        Image.ID.remove("FPX")
    if int(Image.__version__.split(".")[0]) < 13:
        Image.OPEN.pop("TIFF", None)
        Image.SAVE.pop("TIFF", None)
        Image.SAVE_ALL.pop("TIFF", None)
        if "TIFF" in Image.ID:
            Image.ID.remove("TIFF")


remove_flashpix()
