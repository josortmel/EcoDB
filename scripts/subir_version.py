"""Raise EcoDB's version in every place it lives (#1362). From the repo root:

    python scripts/subir_version.py 0.26.0

Changes api/version.py and the three `image: ecodb-api:` tags of docker-compose.yml (api, worker, ecodb-cell), and
opens the section `## [X.Y.Z] — <today>` at the top of CHANGELOG.md for you to write. Then: a release/X.Y.Z PR; when it
is merged into main, CI publishes the release vX.Y.Z with that section as its notes. Build the new image (and deploy)
AFTER the merge: the compose file will name a tag that does not exist yet, and the api service has a `build:` section,
so a `docker compose up` before building would build whatever is in the working tree.
"""

import datetime
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        sys.exit("uso: python scripts/subir_version.py X.Y.Z")
    new = sys.argv[1]

    version_py = REPO / "api" / "version.py"
    text = version_py.read_text(encoding="utf-8")
    old = re.search(r'^__version__ = "([^"]+)"$', text, re.M).group(1)
    if tuple(map(int, new.split("."))) <= tuple(map(int, old.split("."))):
        sys.exit(f"{new} no es mayor que la versión actual {old}")
    version_py.write_text(text.replace(f'__version__ = "{old}"', f'__version__ = "{new}"'), encoding="utf-8")

    compose = REPO / "docker-compose.yml"
    text = compose.read_text(encoding="utf-8")
    pattern = re.compile(rf"^(\s*image:\s*ecodb-api:){re.escape(old)}(\s*)$", re.M)
    text, n = pattern.subn(rf"\g<1>{new}\g<2>", text)
    if n != 3:
        sys.exit(f"esperaba 3 «image: ecodb-api:{old}» en docker-compose.yml y hay {n}: no toco nada más")
    compose.write_text(text, encoding="utf-8")

    changelog = REPO / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    if f"## [{new}]" not in text:
        first = text.index("\n## [")
        today = datetime.date.today().isoformat()
        text = text[: first + 1] + f"## [{new}] — {today}\n\n- (qué cambia en esta versión)\n\n" + text[first + 1 :]
        changelog.write_text(text, encoding="utf-8")

    print(f"{old} → {new}: api/version.py, 3 etiquetas de ecodb-api en docker-compose.yml y CHANGELOG.md.")
    print(
        "Escribe el apartado del CHANGELOG, abre el PR release/" + new + " y construye la imagen después de fusionar."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
