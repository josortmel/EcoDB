"""EcoDB Graph Purge — Dry Run

Genera report de nodos candidatos a eliminación sin tocar la BD.
Review the dry-run report. Si OK, ejecutar con --execute.

Reglas de purga:
  1. Nodos con >8 palabras (frases descriptivas, no entidades)
  2. Nodos que parecen rutas de archivo (contienen \\ o / con extension)
  3. Nodos huérfanos post-purga (sin tripletas)

Uso:
  python purge_graph_dryrun.py              # solo report
  python purge_graph_dryrun.py --execute    # purga real tras confirmación
"""
import asyncio
import asyncpg
import os
import sys
from datetime import datetime, timezone

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ecodb:ecodb_dev_pass@localhost:5434/ecodb"
)

MAX_WORDS = 8

async def get_candidates(conn):
    """Identifica nodos candidatos a purga por cada regla."""

    # Regla 1: nodos >8 palabras
    long_nodes = await conn.fetch("""
        SELECT n.id, n.name, array_length(string_to_array(n.name, ' '), 1) as word_count,
               count(DISTINCT t.id) as triple_count
        FROM nodes n
        LEFT JOIN triples t ON t.subject_id = n.id OR t.object_id = n.id
        WHERE array_length(string_to_array(n.name, ' '), 1) > $1
        GROUP BY n.id, n.name
        ORDER BY array_length(string_to_array(n.name, ' '), 1) DESC
    """, MAX_WORDS)

    # Regla 2: nodos que parecen rutas de archivo
    path_nodes = await conn.fetch("""
        SELECT n.id, n.name,
               count(DISTINCT t.id) as triple_count
        FROM nodes n
        LEFT JOIN triples t ON t.subject_id = n.id OR t.object_id = n.id
        WHERE (n.name LIKE '%%\\%%' OR n.name LIKE '%%/%%')
          AND n.name ~ '\\.[a-zA-Z]{1,4}$'
          AND n.id NOT IN (
              SELECT id FROM nodes
              WHERE array_length(string_to_array(name, ' '), 1) > $1
          )
        GROUP BY n.id, n.name
        ORDER BY n.name
    """, MAX_WORDS)

    return long_nodes, path_nodes

async def get_stats(conn):
    """Estadísticas generales del grafo."""
    nodes = await conn.fetchval("SELECT count(*) FROM nodes")
    triples = await conn.fetchval("SELECT count(*) FROM triples")
    predicates = await conn.fetchval("SELECT count(DISTINCT predicate) FROM triples")
    return nodes, triples, predicates

async def count_affected_triples(conn, node_ids):
    """Cuenta tripletas que se eliminarían en cascada."""
    if not node_ids:
        return 0
    return await conn.fetchval("""
        SELECT count(*) FROM triples
        WHERE subject_id = ANY($1) OR object_id = ANY($1)
    """, node_ids)

async def execute_purge(conn, node_ids):
    """Ejecuta la purga real."""
    if not node_ids:
        return 0, 0

    async with conn.transaction():
        # Eliminar tripletas primero (FK)
        await conn.execute("""
            DELETE FROM triples
            WHERE subject_id = ANY($1) OR object_id = ANY($1)
        """, node_ids)

        # Eliminar memory_entity_links
        await conn.execute("""
            DELETE FROM memory_entity_links
            WHERE entity_node_id = ANY($1::bigint[])
        """, node_ids)

        # Eliminar nodos
        await conn.execute("""
            DELETE FROM nodes WHERE id = ANY($1)
        """, node_ids)

        # Eliminar nodos huérfanos (sin tripletas restantes)
        orphan_count = await conn.fetchval("""
            SELECT count(*) FROM nodes
            WHERE id NOT IN (SELECT subject_id FROM triples)
              AND id NOT IN (SELECT object_id FROM triples)
        """)
        await conn.execute("""
            DELETE FROM nodes
            WHERE id NOT IN (SELECT subject_id FROM triples)
              AND id NOT IN (SELECT object_id FROM triples)
        """)

    return len(node_ids), orphan_count or 0

async def main():
    execute = "--execute" in sys.argv

    conn = await asyncpg.connect(DATABASE_URL)

    # Stats antes
    nodes_before, triples_before, preds_before = await get_stats(conn)
    print(f"{'='*60}")
    print(f"EcoDB Graph Purge {'DRY RUN' if not execute else 'EXECUTING'}")
    print(f"{'='*60}")
    print(f"\nESTADO ANTES:")
    print(f"  Nodos: {nodes_before}")
    print(f"  Tripletas: {triples_before}")
    print(f"  Predicados únicos: {preds_before}")

    # Obtener candidatos
    long_nodes, path_nodes = await get_candidates(conn)

    all_purge_ids = [r["id"] for r in long_nodes] + [r["id"] for r in path_nodes]
    affected_triples = await count_affected_triples(conn, all_purge_ids)

    # Report Regla 1
    print(f"\n{'='*60}")
    print(f"REGLA 1: Nodos >8 palabras (frases, no entidades)")
    print(f"{'='*60}")
    print(f"Candidatos: {len(long_nodes)}")
    print(f"\nMuestra (primeros 50):")
    for r in long_nodes[:50]:
        name_preview = r["name"][:70].replace("\n", " ")
        print(f"  [{r['id']}] ({r['word_count']} words, {r['triple_count']} triples) {name_preview}...")
    if len(long_nodes) > 50:
        print(f"  ... y {len(long_nodes) - 50} más")

    # Report Regla 2
    print(f"\n{'='*60}")
    print(f"REGLA 2: Nodos que parecen rutas de archivo")
    print(f"{'='*60}")
    print(f"Candidatos: {len(path_nodes)}")
    for r in path_nodes[:30]:
        name_preview = r["name"][:70].replace("\n", " ")
        print(f"  [{r['id']}] ({r['triple_count']} triples) {name_preview}")
    if len(path_nodes) > 30:
        print(f"  ... y {len(path_nodes) - 30} más")

    # Resumen
    print(f"\n{'='*60}")
    print(f"RESUMEN DE IMPACTO")
    print(f"{'='*60}")
    print(f"  Nodos a purgar: {len(all_purge_ids)} de {nodes_before} ({100*len(all_purge_ids)//nodes_before}%)")
    print(f"    - Por >8 palabras: {len(long_nodes)}")
    print(f"    - Por ruta archivo: {len(path_nodes)}")
    print(f"  Tripletas afectadas: {affected_triples}")
    print(f"  Nodos restantes (estimado): ~{nodes_before - len(all_purge_ids)}")
    print(f"  + huérfanos que se eliminarán post-purga")

    if execute:
        print(f"\n{'='*60}")
        print(f"EJECUTANDO PURGA...")
        print(f"{'='*60}")
        nodes_deleted, orphans_deleted = await execute_purge(conn, all_purge_ids)

        nodes_after, triples_after, preds_after = await get_stats(conn)
        print(f"\nESTADO DESPUÉS:")
        print(f"  Nodos: {nodes_after} (eliminados: {nodes_before - nodes_after}, de los cuales {orphans_deleted} huérfanos)")
        print(f"  Tripletas: {triples_after} (eliminadas: {triples_before - triples_after})")
        print(f"  Predicados únicos: {preds_after} (eliminados: {preds_before - preds_after})")
        print(f"\nPurga completada: {datetime.now(timezone.utc).isoformat()}")
    else:
        print(f"\n--- DRY RUN: no se ha tocado nada. Ejecutar con --execute para purgar. ---")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
