import asyncio, asyncpg, os, json, sys
sys.path.insert(0, '/app')

GRAPH_NAME = "ecodb_graph"

async def test():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])

    # Insert test node
    row = await conn.fetchrow(
        "INSERT INTO nodes (name, type, status) VALUES ('__trigger_test__', 'concepto', 'active') RETURNING id"
    )
    sql_id = row['id']
    print(f"Inserted SQL node id={sql_id}")

    # Check AGE
    params = json.dumps({"name": "__trigger_test__"})
    age_row = await conn.fetchrow(
        f"SELECT * FROM cypher('{GRAPH_NAME}', $$ MATCH (n:Entity {{name: $name}}) RETURN n.sql_id $$, $1::agtype) AS (sid agtype)",
        params
    )
    if age_row:
        print(f"AGE node found ✅ sql_id={age_row['sid']}")
    else:
        print("AGE node NOT found ❌")

    # Clean up SQL (trigger should remove from AGE)
    await conn.execute("DELETE FROM nodes WHERE name = '__trigger_test__'")
    print("SQL node deleted")

    # Verify AGE cleanup
    age_after = await conn.fetchrow(
        f"SELECT * FROM cypher('{GRAPH_NAME}', $$ MATCH (n:Entity {{name: $name}}) RETURN n.sql_id $$, $1::agtype) AS (sid agtype)",
        params
    )
    if age_after is None:
        print("AGE node removed ✅")
    else:
        print("AGE node still present ❌")

    await conn.close()

asyncio.run(test())
