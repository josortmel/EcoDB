"""#1362: EcoDB has ONE version, api/version.py, and everything that shows it agrees (Pepe's decision 139, 23-nov).

Before there were three that never talked to each other: v1.3.2 (tags, CHANGELOG, releases), 0.25.0 (the ecodb-api
image in docker-compose.yml) and 0.9.0 (settings.API_VERSION, what /health said). Pure test: no database.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "api"))

import settings  # noqa: E402
from version import __version__  # noqa: E402


def test_the_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_health_says_the_same_version():
    assert settings.API_VERSION == __version__


def test_every_ecodb_api_image_in_compose_carries_the_version():
    # api, worker and ecodb-cell run the same image; a tag that falls behind would run other code under one name.
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    tags = re.findall(r"^\s*image:\s*ecodb-api:(\S+)\s*$", compose, re.M)
    assert len(tags) == 3
    assert set(tags) == {__version__}


def test_the_changelog_explains_the_numbering():
    # From 1.4.0 the public v1.x releases and the image tag are one number; the old internal 0.2x is explained.
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "api/version.py" in changelog
    assert "v1.x" in changelog
    assert "0.25.0" in changelog
