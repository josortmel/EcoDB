import asyncio, asyncpg, os, json

GRAPH_NAME = "ecodb_graph"

async def sync():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'])
    async with pool.acquire() as conn:
        # BEFORE count
        row = await conn.fetchrow(
            f"SELECT * FROM cypher('{GRAPH_NAME}', $$ MATCH (n:Entity) RETURN count(n) $$) AS (cnt agtype)"
        )
        before = int(str(row['cnt']).strip('"'))
        print(f'BEFORE AGE nodes: {before}')

        # Find SQL nodes not in AGE
        sql_nodes = await conn.fetch("SELECT id, name FROM nodes WHERE status='active' ORDER BY id")
        print(f'SQL active nodes: {len(sql_nodes)}')

        inserted = 0
        for n in sql_nodes:
            params = json.dumps({"sql_id": n['id']})
            exists = await conn.fetchrow(
                f"SELECT * FROM cypher('{GRAPH_NAME}', $$ MATCH (n:Entity {{sql_id: $sql_id}}) RETURN id(n) $$, $1::agtype) AS (nid agtype)",
                params
            )
            if exists is None:
                p = json.dumps({"name": n['name'], "sql_id": n['id']})
                await conn.execute(
                    f"SELECT * FROM cypher('{GRAPH_NAME}', $$ CREATE (n:Entity {{name: $name, sql_id: $sql_id}}) RETURN id(n) $$, $1::agtype) AS (nid agtype)",
                    p
                )
                inserted += 1

        print(f'Inserted into AGE: {inserted}')

        row2 = await conn.fetchrow(
            f"SELECT * FROM cypher('{GRAPH_NAME}', $$ MATCH (n:Entity) RETURN count(n) $$) AS (cnt agtype)"
        )
        after = int(str(row2['cnt']).strip('"'))
        print(f'AFTER AGE nodes: {after}')
    await pool.close()

asyncio.run(sync())
