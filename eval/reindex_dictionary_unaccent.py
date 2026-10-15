"""#513 — re-enlaza las memorias con el diccionario de entidades DESPUÉS del #478 (búsqueda sin tildes)
y de las fusiones del #479. Sustituye, para este uso, a reindex_memories.py, que buscaba el nodo con
lower(name) = normalize_name(texto): desde el #478, normalize_name quita las tildes y aquello enlazaba con
el gemelo sin tilde.

Reglas: (1) solo nodos ACTIVOS (nunca uno fusionado); (2) el nodo se busca por f_unaccent(lower(name)),
el mismo índice que usa search_nodes; (3) si hay MÁS DE UN nodo activo para la misma clave (los grupos
distintos que quedaron a propósito: él/El, Pärt/Part), no elige: lo cuenta como ambiguo y no enlaza;
(4) ON CONFLICT DO NOTHING: es idempotente.

Uso, dentro de ecodb-api (allí están el diccionario y el DATABASE_URL):
  python /tmp/reindex_dictionary_unaccent.py            → simulacro: cuenta, no escribe
  python /tmp/reindex_dictionary_unaccent.py --apply    → escribe
"""
import asyncio, os, sys, time, collections
sys.path.insert(0, "/app")
import asyncpg

APPLY = "--apply" in sys.argv


async def main():
    from gliner_service import extract_entities, load_dictionary_to_cache
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=4)
    print("diccionario:", await load_dictionary_to_cache(pool), "entradas")
    async with pool.acquire() as c:
        mems = await c.fetch("SELECT id, content FROM memories "
                             "WHERE staleness IS NULL OR staleness NOT IN ('dormant','archived')")
        links_before = await c.fetchval("SELECT count(*) FROM memory_entity_links")
        # clave sin tildes -> nodos ACTIVOS
        rows = await c.fetch("SELECT id, f_unaccent(lower(name)) AS k FROM nodes WHERE status = 'active'")
    by_key = collections.defaultdict(list)
    for r in rows:
        by_key[r["k"]].append(r["id"])
    print("memorias:", len(mems), "| enlaces antes:", links_before, "| nodos activos:", len(rows))

    t0 = time.time()
    would, created, ambiguous, missing, errors = 0, 0, collections.Counter(), collections.Counter(), 0
    async with pool.acquire() as c:
        unaccent = lambda s: c.fetchval("SELECT f_unaccent(lower($1))", s)
        cache = {}
        for m in mems:
            try:
                ents = await extract_entities(m["content"], dictionary_only=True)
            except Exception as e:  # noqa: BLE001
                errors += 1
                if errors <= 5:
                    print("  error", m["id"], e)
                continue
            for name in dict.fromkeys(e["text"] for e in ents):
                if name not in cache:
                    cache[name] = await unaccent(name)
                ids = by_key.get(cache[name], [])
                if len(ids) > 1:
                    ambiguous[name] += 1
                    continue
                if not ids:
                    missing[name] += 1
                    continue
                exists = await c.fetchval("SELECT 1 FROM memory_entity_links WHERE memory_id=$1 AND entity_node_id=$2",
                                          m["id"], ids[0])
                if exists:
                    continue
                would += 1
                if APPLY:
                    res = await c.execute("INSERT INTO memory_entity_links (memory_id, entity_node_id) "
                                          "VALUES ($1, $2) ON CONFLICT DO NOTHING", m["id"], ids[0])
                    created += res.endswith(" 1")
        links_after = await c.fetchval("SELECT count(*) FROM memory_entity_links")
        to_merged = await c.fetchval("SELECT count(*) FROM memory_entity_links l JOIN nodes n ON n.id = l.entity_node_id "
                                     "WHERE n.status = 'merged'")
    print(f"{'APLICADO' if APPLY else 'SIMULACRO'} en {time.time() - t0:.1f} s")
    print("enlaces nuevos:", would, "| creados:", created, "| enlaces ahora:", links_after, "| errores:", errors)
    print("enlaces que apuntan a un nodo fusionado (toda la base):", to_merged)
    print("ambiguos (no enlazados):", dict(ambiguous.most_common(10)))
    print("entradas del diccionario sin nodo activo (no enlazadas):", len(missing), dict(missing.most_common(8)))
    await pool.close()

asyncio.run(main())
