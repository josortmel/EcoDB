import asyncio, asyncpg, os, sys, time
sys.path.insert(0, '/app')

async def reindex():
    url = os.environ.get('DATABASE_URL')
    pool = await asyncpg.create_pool(url)

    # Load dictionary cache first
    from gliner_service import extract_entities, load_dictionary_to_cache
    from entity_normalization import normalize_name

    cache_count = await load_dictionary_to_cache(pool)
    print(f"Dictionary cache loaded: {cache_count} entries")

    # Get all active non-dormant memories
    async with pool.acquire() as conn:
        memories = await conn.fetch(
            "SELECT id, content FROM memories "
            "WHERE staleness IS NULL OR staleness NOT IN ('dormant', 'archived')"
        )
        links_before = await conn.fetchval("SELECT count(*) FROM memory_entity_links")

    print(f"Memories to reindex: {len(memories)}")
    print(f"memory_entity_links before: {links_before}")

    start = time.time()
    new_links = 0
    errors = 0

    for mem in memories:
        try:
            entities = await extract_entities(mem["content"], dictionary_only=True)
            if not entities:
                continue
            unique_names = list(dict.fromkeys(normalize_name(e["text"]) for e in entities))
            async with pool.acquire() as conn:
                for name_norm in unique_names:
                    # Find node by normalized name
                    node = await conn.fetchrow(
                        "SELECT id FROM nodes WHERE lower(name) = $1 AND status = 'active' LIMIT 1",
                        name_norm
                    )
                    if node:
                        result = await conn.execute(
                            "INSERT INTO memory_entity_links (memory_id, entity_node_id) "
                            "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                            mem["id"], node["id"],
                        )
                        if "INSERT 0 1" in result:
                            new_links += 1
        except Exception as exc:
            errors += 1
            if errors <= 5:
                print(f"  Error memory {mem['id']}: {exc}")

    elapsed = time.time() - start

    async with pool.acquire() as conn:
        links_after = await conn.fetchval("SELECT count(*) FROM memory_entity_links")

    print(f"\nDone in {elapsed:.1f}s")
    print(f"New links created: {new_links}")
    print(f"memory_entity_links: {links_before} → {links_after} (+{links_after - links_before})")
    print(f"Errors: {errors}")

    await pool.close()

asyncio.run(reindex())
