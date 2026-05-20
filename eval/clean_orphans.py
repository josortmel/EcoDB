import asyncio, asyncpg, os

async def clean():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'])
    async with pool.acquire() as conn:
        before = await conn.fetchval("SELECT count(*) FROM memory_entity_links")

        orphans = await conn.fetchval("""
            SELECT count(*) FROM memory_entity_links mel
            WHERE NOT EXISTS (
                SELECT 1 FROM nodes n WHERE n.id = mel.entity_node_id AND n.status = 'active'
            )
        """)

        result = await conn.execute("""
            DELETE FROM memory_entity_links mel
            WHERE NOT EXISTS (
                SELECT 1 FROM nodes n WHERE n.id = mel.entity_node_id AND n.status = 'active'
            )
        """)

        after = await conn.fetchval("SELECT count(*) FROM memory_entity_links")
        print(f"BEFORE: {before}")
        print(f"Orphans deleted: {orphans}")
        print(f"AFTER: {after}")
    await pool.close()

asyncio.run(clean())
