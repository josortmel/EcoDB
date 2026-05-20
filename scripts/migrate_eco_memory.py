"""
One-time migration: ChromaDB → EcoDB.

Field mappings:
- ChromaDB document → memories.content
- meta.summary → memories.metadata.summary (JSONB)
- meta.tags (CSV string) → memories.tags TEXT[]
- meta.weight (float) → memories.weight_base
- meta.timestamp (ISO) → memories.created_at
- meta.access_count → memories.access_count (default 0 if missing)
- meta.autor → resolved via agent lookup

Author normalization:
- Unknown/legacy author names are mapped to canonical agent identifiers or SIN_AUTOR.

Visibility rules:
- Private agents → 'private'
- Shared/infrastructure agents → 'public'

Re-embedding:
- Source: mxbai-embed-large 1024 dims → Target: Jina v4 512 dims (prompt_name='passage', truncate_dim=512)

Usage:
  python scripts/migrate_eco_memory.py --dry-run
  python scripts/migrate_eco_memory.py --execute

Prerequisites:
- ChromaDB path set via CHROMA_PATH env var (read-only access only).
- ecodb-postgres (5435) accessible.
- ecodb-embeddings (8090) running.
- EcoDB memories/agent_identity tables empty.
- Raw chroma_db backup already taken.

Rollback if failed: TRUNCATE memories + agent_identity in EcoDB. ChromaDB is never modified.
"""
from __future__ import annotations

import os
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from typing import Optional

import asyncpg
import chromadb
import httpx

CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_db")
DEST_DSN = "postgres://ecodb:ecodb_test_pass@localhost:5435/ecodb"
EMB_URL = "http://localhost:8090/embed/text"

AUTOR_LEGACY = "default"
AUTOR_DESCONOCIDO = "SIN_AUTOR"
EMB_DIM = 512
EMB_BATCH_SIZE = 16
EMB_TIMEOUT = 120.0
WORKSPACE_ID = 1
PROJECT_ID = 1
EMBEDDING_MODEL_TAG = "jina-v4"

# Populate with any legacy author names from your source system that need
# remapping to canonical agent identifiers in EcoDB.
# Example: {"OldAgentName": "new-agent-identifier"}
AUTHOR_REMAP: dict[str, str] = {}

# Default visibility per agent identifier. Agents not listed here default to "public".
VISIBILITY_BY_AUTHOR: dict[str, str] = {
    "SIN_AUTOR": "public",
}


async def embed_batch(client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
    payload = {
        "texts": texts,
        "task": "retrieval",
        "prompt_name": "passage",
        "truncate_dim": EMB_DIM,
    }
    r = await client.post(EMB_URL, json=payload, timeout=EMB_TIMEOUT)
    r.raise_for_status()
    return r.json()["embeddings"]


def vec_to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def parse_tags(tags_str: Optional[str]) -> list[str]:
    """tags vienen como CSV string. Devuelve lista limpia (sin vacios, trim, dedup)."""
    if not tags_str:
        return []
    raw = [t.strip() for t in tags_str.split(",")]
    seen = set()
    result = []
    for t in raw:
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result


def parse_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def resolve_author(raw_author: Optional[str]) -> str:
    """Resolve and remap raw author string to canonical agent identifier."""
    if not raw_author:
        return AUTOR_LEGACY
    return AUTHOR_REMAP.get(raw_author, raw_author)


def visibility_for(author: str) -> str:
    return VISIBILITY_BY_AUTHOR.get(author, "public")


async def main(dry_run: bool) -> int:
    print(f"=== migrate_eco_memory.py {'DRY RUN' if dry_run else 'EXECUTE'} ===\n", flush=True)

    # === Origen: ChromaDB readonly ===
    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        col_memory = chroma.get_collection("eco_memory")
        col_identity = chroma.get_collection("eco_identity")
    except Exception as e:
        print(f"ERROR conectando ChromaDB: {e}", flush=True)
        return 1

    n_memory = col_memory.count()
    n_identity = col_identity.count()

    # === Destino: EcoDB ===
    dest = await asyncpg.connect(DEST_DSN)

    # Lookup agent identifier → id
    agent_rows = await dest.fetch("SELECT id, identifier FROM agents")
    agent_id_by_name: dict[str, int] = {r["identifier"]: r["id"] for r in agent_rows}
    print(f"AGENTS seed disponibles: {agent_id_by_name}", flush=True)

    n_dest_memories = await dest.fetchval("SELECT COUNT(*) FROM memories")
    n_dest_identity = await dest.fetchval("SELECT COUNT(*) FROM agent_identity")
    print(f"DESTINO ecodb (5435):", flush=True)
    print(f"  memories: {n_dest_memories}, agent_identity: {n_dest_identity}", flush=True)
    print(f"ORIGEN ChromaDB:", flush=True)
    print(f"  eco_memory: {n_memory}", flush=True)
    print(f"  eco_identity: {n_identity}", flush=True)
    print(f"  (eco_memory_papelera collection skipped)", flush=True)
    print()

    if n_dest_memories != 0 or n_dest_identity != 0:
        print("ERROR: destino no esta vacio. Aborta.", flush=True)
        await dest.close()
        return 1

    # === Pre-check: invariante temporal de autor ===
    all_memory = col_memory.get(include=["metadatas"])
    sin_autor_max_ts = None
    con_autor_min_ts = None
    for m in all_memory["metadatas"]:
        ts = m.get("timestamp")
        if not ts:
            continue
        if not m.get("autor"):
            if sin_autor_max_ts is None or ts > sin_autor_max_ts:
                sin_autor_max_ts = ts
        else:
            if con_autor_min_ts is None or ts < con_autor_min_ts:
                con_autor_min_ts = ts
    print(f"Invariante temporal:", flush=True)
    print(f"  sin-autor max timestamp: {sin_autor_max_ts}", flush=True)
    print(f"  con-autor min timestamp: {con_autor_min_ts}", flush=True)
    if sin_autor_max_ts and con_autor_min_ts:
        if sin_autor_max_ts < con_autor_min_ts:
            print(f"  OK — sin-autor estrictamente anteriores. Hotfix → Eco aplicable.", flush=True)
        else:
            print(f"  ALARMA — sin-autor solapa con con-autor. NO aplicar hotfix automatico. ABORT.", flush=True)
            await dest.close()
            return 1
    print()

    # === Stats per-autor (tras remap) ===
    autor_stats: dict[str, int] = {}
    for m in all_memory["metadatas"]:
        a = resolve_author(m.get("autor"))
        autor_stats[a] = autor_stats.get(a, 0) + 1
    print(f"Author distribution after remapping:", flush=True)
    for a, n in sorted(autor_stats.items(), key=lambda x: -x[1]):
        vis = visibility_for(a)
        in_seed = a in agent_id_by_name
        print(f"  {a}: {n} (visibility={vis}, in_agents_seed={'YES' if in_seed else 'NO'})", flush=True)

    # Verificar que TODOS los autores resueltos existen en agents
    missing = [a for a in autor_stats if a not in agent_id_by_name]
    if missing:
        print(f"  ERROR: autores no presentes en agents seed: {missing}", flush=True)
        await dest.close()
        return 1
    print()

    if dry_run:
        # Sample 2 memorias
        print(f"=== DRY RUN ===", flush=True)
        sample = col_memory.get(limit=2, include=["metadatas", "documents"])
        for i in range(len(sample["ids"])):
            m = sample["metadatas"][i]
            d = sample["documents"][i]
            a = resolve_author(m.get("autor"))
            print(f"  Sample {i+1}: id={sample['ids'][i][:8]}... raw_author={m.get('autor')!r} → {a}", flush=True)
            print(f"    document ({len(d)} chars): {d[:100]!r}...", flush=True)
            print(f"    summary: {m.get('summary', '')[:80]!r}", flush=True)
            print(f"    tags raw: {m.get('tags', '')!r} → parsed: {parse_tags(m.get('tags'))}", flush=True)
            print(f"    weight: {m.get('weight')} access_count: {m.get('access_count', 0)}", flush=True)
            print(f"    visibility: {visibility_for(a)}", flush=True)
            print()

        # Identidad sample
        print(f"=== eco_identity dry sample ===", flush=True)
        idy = col_identity.get(limit=2, include=["metadatas", "documents"])
        for i in range(len(idy["ids"])):
            m = idy["metadatas"][i]
            a = resolve_author(m.get("autor"))
            print(f"  id={idy['ids'][i][:8]}... raw_author={m.get('autor')!r} → {a} orden={m.get('orden')} content_len={len(idy['documents'][i])}", flush=True)

        await dest.close()
        return 0

    # === EXECUTE ===
    t_start = time.time()
    async with httpx.AsyncClient() as client:

        # FASE 1 — Migrar 939 recuerdos eco_memory
        print(f"=== FASE 1 — migrar {n_memory} recuerdos ===", flush=True)
        all_data = col_memory.get(include=["metadatas", "documents"])
        ids = all_data["ids"]
        docs = all_data["documents"]
        metas = all_data["metadatas"]

        inserted = 0
        skipped = 0
        for batch_start in range(0, len(ids), EMB_BATCH_SIZE):
            batch_end = min(batch_start + EMB_BATCH_SIZE, len(ids))
            batch_docs = [docs[i] for i in range(batch_start, batch_end)]
            batch_embeddings = await embed_batch(client, batch_docs)

            for i, emb in zip(range(batch_start, batch_end), batch_embeddings):
                m = metas[i]
                doc = docs[i]
                raw_author = m.get("autor")
                author_name = resolve_author(raw_author)
                agent_id = agent_id_by_name[author_name]
                vis = visibility_for(author_name)
                tags = parse_tags(m.get("tags"))
                weight = float(m.get("weight") or 0.5)
                access_count = int(m.get("access_count") or 0)
                ts = parse_timestamp(m.get("timestamp"))
                summary = m.get("summary")
                emb_literal = vec_to_pgvector(emb)

                try:
                    await dest.execute(
                        """
                        INSERT INTO memories
                          (user_id, agent_id, workspace_id, project_id, type,
                           content_type, visibility, content, summary, tags,
                           weight, weight_base, access_count, embedding,
                           embedding_model, created_at)
                        VALUES (1, $1, $2, $3, 'tecnico'::memory_type,
                                'text'::content_modality, $4::visibility, $5, $6, $7,
                                $8, $8, $9, $10::vector,
                                $11, $12)
                        """,
                        agent_id, WORKSPACE_ID, PROJECT_ID,
                        vis, doc, summary, tags,
                        weight, access_count, emb_literal,
                        EMBEDDING_MODEL_TAG, ts or datetime.now(),
                    )
                    inserted += 1
                except Exception as e:
                    print(f"  WARN id={ids[i][:8]} skip por: {type(e).__name__}: {str(e)[:100]}", flush=True)
                    skipped += 1

            if (batch_start // EMB_BATCH_SIZE) % 10 == 0:
                elapsed = time.time() - t_start
                print(f"  batch {batch_end}/{len(ids)} ({elapsed:.1f}s, inserted={inserted} skipped={skipped})", flush=True)
        t1 = time.time()
        print(f"  FASE 1 done: inserted={inserted} skipped={skipped} en {t1 - t_start:.1f}s", flush=True)

        # FASE 2 — Migrar eco_identity
        print(f"\n=== FASE 2 — migrar {n_identity} fragmentos identidad ===", flush=True)
        idy_data = col_identity.get(include=["metadatas", "documents"])
        idy_ids = idy_data["ids"]
        idy_docs = idy_data["documents"]
        idy_metas = idy_data["metadatas"]

        idy_inserted = 0
        idy_skipped = 0
        for batch_start in range(0, len(idy_ids), EMB_BATCH_SIZE):
            batch_end = min(batch_start + EMB_BATCH_SIZE, len(idy_ids))
            for i in range(batch_start, batch_end):
                m = idy_metas[i]
                doc = idy_docs[i]
                raw_author = m.get("autor")
                author_name = resolve_author(raw_author)
                agent_id = agent_id_by_name[author_name]
                orden = m.get("orden", i)
                try:
                    await dest.execute(
                        """
                        INSERT INTO agent_identity
                          (agent_id, organization_id, version, fragment_idx, content)
                        VALUES ($1, NULL, 1, $2, $3)
                        """,
                        agent_id, int(orden), doc,
                    )
                    idy_inserted += 1
                except Exception as e:
                    print(f"  WARN identity id={idy_ids[i][:8]} skip: {type(e).__name__}: {str(e)[:100]}", flush=True)
                    idy_skipped += 1
        t2 = time.time()
        print(f"  FASE 2 done: inserted={idy_inserted} skipped={idy_skipped} en {t2 - t1:.1f}s", flush=True)

    # === Verificacion final ===
    print(f"\n=== VERIFICACION FINAL ===", flush=True)
    n_memories_final = await dest.fetchval("SELECT COUNT(*) FROM memories")
    n_identity_final = await dest.fetchval("SELECT COUNT(*) FROM agent_identity")
    n_emb_null = await dest.fetchval("SELECT COUNT(*) FROM memories WHERE embedding IS NULL")
    n_private = await dest.fetchval("SELECT COUNT(*) FROM memories WHERE visibility = 'private'")
    n_public = await dest.fetchval("SELECT COUNT(*) FROM memories WHERE visibility = 'public'")
    by_author = await dest.fetch(
        """SELECT a.identifier, COUNT(*) AS n FROM memories m
           JOIN agents a ON a.id = m.agent_id GROUP BY a.identifier ORDER BY n DESC"""
    )
    by_identity = await dest.fetch(
        """SELECT a.identifier, COUNT(*) AS n FROM agent_identity ai
           JOIN agents a ON a.id = ai.agent_id GROUP BY a.identifier ORDER BY n DESC"""
    )

    print(f"  memories: {n_memories_final} (esperado {n_memory}, skipped {skipped})", flush=True)
    print(f"  memories con embedding: {n_memories_final - n_emb_null} / {n_memories_final}", flush=True)
    print(f"  memories visibility: private={n_private} public={n_public}", flush=True)
    print(f"  memories por autor:", flush=True)
    for r in by_author:
        print(f"    {r['identifier']}: {r['n']}", flush=True)
    print(f"  agent_identity: {n_identity_final} (esperado {n_identity}, skipped {idy_skipped})", flush=True)
    print(f"  agent_identity por agente:", flush=True)
    for r in by_identity:
        print(f"    {r['identifier']}: {r['n']}", flush=True)
    print(f"\nTOTAL elapsed: {time.time() - t_start:.1f}s", flush=True)

    await dest.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(dry_run=args.dry_run)))
