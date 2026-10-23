"""#717 (23-oct): the cell wrote memories with raw SQL and no embedding — 97 active memories
(90 identity tensions, 5 skills, 2 técnico) were invisible to vector search. Every INSERT
INTO memories in cell_worker must carry an embedding, and an embeddings outage must not
cost the memory (it is saved without one and left for the backfill). Offline: respx."""
import asyncio
import os
import re
import sys
from pathlib import Path

import httpx
import respx

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))
from conftest import TEST_DB_URL  # noqa: E402

os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
import cell_worker as cw  # noqa: E402
import settings  # noqa: E402

EMBED = f"{settings.EMBEDDINGS_URL}/embed/text"


def test_every_cell_memory_insert_carries_an_embedding():
    src = (API_DIR / "cell_worker.py").read_text(encoding="utf-8")
    inserts = re.findall(r"INSERT INTO memories\s*\(([^)]*)\)", src)
    assert inserts, "no INSERT INTO memories found"
    missing = [cols.split() for cols in inserts if "embedding" not in cols]
    assert missing == [], f"INSERT INTO memories without embedding: {missing}"


@respx.mock
def test_embed_for_memory_returns_a_vector_literal():
    respx.post(EMBED).mock(return_value=httpx.Response(200, json={
        "embeddings": [[0.5] * settings.EMBEDDING_DIM]}))
    vec = asyncio.run(cw._embed_for_memory("Identity tension: x vs y"))
    assert vec.startswith("[") and vec.count(",") == settings.EMBEDDING_DIM - 1


@respx.mock
def test_embed_for_memory_survives_an_outage():
    respx.post(EMBED).mock(side_effect=httpx.ConnectError("down"))
    assert asyncio.run(cw._embed_for_memory("Identity tension: x vs y")) is None
