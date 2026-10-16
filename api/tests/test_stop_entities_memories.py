"""#443 — save_memory must honour stop_entities, like the document pipeline does.

link_entities_from_content (the memory path) used to create a node and a memory_entity_link for every
name GLiNER or the dictionary returned, even if that name was in stop_entities. Integration against a
real postgres+AGE; extract_entities is replaced so the test needs no GLiNER model.

Run ONLY against a throwaway DB: TEST_DB_PORT=5436 (never the live family DB on 5435).
"""
import asyncio
import sys
import uuid
from pathlib import Path

import asyncpg

from conftest import TEST_DB_URL

sys.path.insert(0, str(Path(__file__).parent.parent))

import gliner_service  # noqa: E402
import graph  # noqa: E402

def _names():
    tag = f"pytest-stop443-{uuid.uuid4().hex[:6]}"
    # STOPPED carries an accent; the stop list stores it without (normalize_name strips accents, #478)
    return tag, f"{tag} Acmé Corp", f"{tag} Kept Entity"


async def _linked_names(conn, memory_id):
    rows = await conn.fetch(
        """SELECT n.name FROM memory_entity_links l JOIN nodes n ON n.id = l.entity_node_id
           WHERE l.memory_id = $1""", memory_id)
    return {r["name"] for r in rows}


async def _scenario(with_stop: bool):
    TAG, STOPPED, KEPT = _names()

    async def _fake_extract(content, *args, **kwargs):
        return [{"text": STOPPED, "label": "organizacion", "score": 1.0, "source": "dictionary"},
                {"text": KEPT, "label": "concepto", "score": 1.0, "source": "dictionary"}]

    conn = await asyncpg.connect(TEST_DB_URL)
    original = gliner_service.extract_entities
    gliner_service.extract_entities = _fake_extract
    try:
        memory_id = await conn.fetchval(
            "INSERT INTO memories (workspace_id, project_id, type, content) "
            "VALUES (1, 1, 'observacion', $1) RETURNING id", f"{TAG} memory")
        if with_stop:
            await conn.execute(
                "INSERT INTO stop_entities (name, name_normalized, reason, created_by) VALUES ($1, $2, $3, 1)",
                STOPPED, gliner_service.normalize_name(STOPPED.replace("é", "e")), TAG)
        count = await graph.link_entities_from_content(conn, memory_id, "irrelevant, extraction is faked")
        names = await _linked_names(conn, memory_id)
        stopped_nodes = await conn.fetchval("SELECT count(*) FROM nodes WHERE name = $1", STOPPED)
        return count, names, stopped_nodes, STOPPED, KEPT
    finally:
        gliner_service.extract_entities = original
        await conn.execute("DELETE FROM memory_entity_links WHERE memory_id IN "
                           "(SELECT id FROM memories WHERE content LIKE $1)", f"{TAG}%")
        await conn.execute("DELETE FROM memories WHERE content LIKE $1", f"{TAG}%")
        await conn.execute("DELETE FROM stop_entities WHERE reason = $1", TAG)
        await conn.close()


def test_stop_entity_is_not_linked_from_a_memory():
    count, names, stopped_nodes, STOPPED, KEPT = asyncio.run(_scenario(with_stop=True))
    assert names == {KEPT}
    assert count == 1
    assert stopped_nodes == 0


def test_without_stop_entity_both_are_linked():
    count, names, _, STOPPED, KEPT = asyncio.run(_scenario(with_stop=False))
    assert names == {STOPPED, KEPT}
    assert count == 2
