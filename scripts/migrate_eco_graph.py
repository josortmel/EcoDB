"""
Migracion eco_graph viejo (5433) -> EcoDB (5435 + AGE). .1.

Decisiones aplicadas :
- 118 literales sin objeto_id -> nodos artificiales `nodes.type='literal'`.
- peso -> `triples.metadata.peso`.
- fecha y origen -> columnas top-level `triples.fecha DATE` y `triples.origen TEXT`.
- document_id columna FK reservada para Fase 4 (NULL aqui).
- Empty authors mapped to 'MIGRATION_DEFAULT'. Explicit author names preserved if present.
- Re-embed con Jina v4 prompt_name='passage', truncate_dim=512.
- Aristas AGE :RELATES_TO {predicate, sql_triple_id}.

Uso:
  python scripts/migrate_eco_graph.py --dry-run    # solo conteos + sample
  python scripts/migrate_eco_graph.py --execute    # migracion real

Pre-requisitos:
- eco-postgres (5433) accesible (auth trust desde 127.0.0.1).
- ecodb-postgres (5435) accesible.
- ecodb-embeddings (8090) vivo.
- EcoDB nodes/triples/predicate_embeddings vacios.
- pg_dump backup origen ya hecho.

Rollback: si falla, TRUNCATE EcoDB tables + DROP graph + recreate. Origen NO se toca.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Optional

import os

import asyncpg
import httpx

ORIG_DSN = os.environ.get("ORIG_DATABASE_URL", "postgres://postgres:ecodb_dev_pass@localhost:5433/eco_graph")
DEST_DSN = "postgres://ecodb:ecodb_test_pass@localhost:5435/ecodb"
EMB_URL = "http://localhost:8090/embed/text"
GRAPH_NAME = "ecodb_graph"

MIGRATION_AUTHOR = "MIGRACION_ECO_GRAPH_2026-05-08"
EMB_DIM = 512
EMB_BATCH_SIZE = 16
EMB_TIMEOUT = 120.0


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


async def create_age_node(conn, name: str, sql_id: int) -> None:
    """Patron de api/graph.py:_ensure_age_node — JSON via 3er arg de cypher() como agtype."""
    params = json.dumps({"name": name, "sql_id": sql_id})
    await conn.execute(
        f"""
        SELECT * FROM cypher('{GRAPH_NAME}', $$
            CREATE (n:Entity {{name: $name, sql_id: $sql_id}})
            RETURN id(n)
        $$, $1::agtype) AS (node_id agtype)
        """,
        params,
    )


async def create_age_edge(conn, sid: int, oid: int, predicate: str, sql_triple_id: int) -> None:
    """Patron de api/graph.py:_create_age_edge ampliado con sql_triple_id."""
    params = json.dumps({
        "sid": sid, "oid": oid, "pred": predicate, "tid": sql_triple_id,
    })
    await conn.execute(
        f"""
        SELECT * FROM cypher('{GRAPH_NAME}', $$
            MATCH (s:Entity {{sql_id: $sid}}), (o:Entity {{sql_id: $oid}})
            CREATE (s)-[r:RELATES_TO {{predicate: $pred, sql_triple_id: $tid}}]->(o)
            RETURN id(r)
        $$, $1::agtype) AS (edge_id agtype)
        """,
        params,
    )


async def main(dry_run: bool) -> int:
    print(f"=== migrate_eco_graph.py {'DRY RUN' if dry_run else 'EXECUTE'} ===\n")

    orig = await asyncpg.connect(ORIG_DSN)
    dest = await asyncpg.connect(DEST_DSN)

    # Setup AGE en la conexion destino
    await dest.execute("LOAD 'age'")
    await dest.execute('SET search_path = public, ag_catalog, "$user"')

    # === Pre-checks ===
    n_nodos = await orig.fetchval("SELECT COUNT(*) FROM nodos")
    n_tripletas = await orig.fetchval("SELECT COUNT(*) FROM tripletas")
    n_literales = await orig.fetchval("""
        SELECT COUNT(DISTINCT objeto_literal) FROM tripletas
        WHERE objeto_literal IS NOT NULL AND objeto_id IS NULL
    """)
    n_predicados = await orig.fetchval("SELECT COUNT(DISTINCT predicado) FROM tripletas")
    n_autores_vacios = await orig.fetchval(
        "SELECT COUNT(*) FROM tripletas WHERE autor IS NULL OR autor = ''"
    )

    n_dest_nodes = await dest.fetchval("SELECT COUNT(*) FROM nodes")
    n_dest_triples = await dest.fetchval("SELECT COUNT(*) FROM triples")
    n_dest_pe = await dest.fetchval("SELECT COUNT(*) FROM predicate_embeddings")
    age_count = await dest.fetchrow(
        f"""SELECT * FROM cypher('{GRAPH_NAME}', $$ MATCH (n) RETURN COUNT(n) $$)
            AS (c agtype)"""
    )
    n_age_nodes = int(str(age_count["c"]).strip('"').strip())

    print(f"ORIGEN eco_graph (5433):")
    print(f"  nodos: {n_nodos}")
    print(f"  tripletas: {n_tripletas}")
    print(f"  literales unicos: {n_literales}")
    print(f"  predicados unicos: {n_predicados}")
    print(f"  autores vacios -> MIGRACION_ECO_GRAPH_2026-05-08: {n_autores_vacios}")
    print(f"DESTINO ecodb (5435):")
    print(f"  nodes: {n_dest_nodes}, triples: {n_dest_triples}, predicate_embeddings: {n_dest_pe}")
    print(f"  AGE ecodb_graph nodes: {n_age_nodes}")
    print()

    if n_dest_nodes != 0 or n_dest_triples != 0 or n_dest_pe != 0 or n_age_nodes != 0:
        print("ERROR: destino no esta vacio. Aborta.")
        await orig.close()
        await dest.close()
        return 1

    if dry_run:
        print(f"=== DRY RUN ===")
        print(f"Migraria: {n_nodos} nodos + {n_literales} literales = {n_nodos + n_literales} nodes EcoDB")
        print(f"           {n_tripletas} tripletas -> triples + aristas AGE")
        print(f"           {n_predicados} predicados unicos -> predicate_embeddings")
        nodos = await orig.fetch("SELECT id, nombre, tipo, descripcion FROM nodos ORDER BY id LIMIT 3")
        print(f"\nSample 3 primeros nodos:")
        for n in nodos:
            print(f"  id={n['id']} nombre={n['nombre']!r} tipo={n['tipo']!r} desc={(n['descripcion'] or '')[:50]!r}")
        literales = await orig.fetch("""
            SELECT DISTINCT objeto_literal FROM tripletas
            WHERE objeto_literal IS NOT NULL AND objeto_id IS NULL ORDER BY objeto_literal LIMIT 3
        """)
        print(f"\nSample 3 primeros literales:")
        for l in literales:
            print(f"  literal={l['objeto_literal']!r}")
        tripletas = await orig.fetch("SELECT * FROM tripletas ORDER BY id LIMIT 1")
        print(f"\nSample primera tripleta:")
        for t in tripletas:
            print(f"  id={t['id']} sujeto_id={t['sujeto_id']} predicado={t['predicado']!r}")
            print(f"  objeto_id={t['objeto_id']} literal={t['objeto_literal']!r}")
            print(f"  autor={t['autor']!r} peso={t['peso']} fecha={t['fecha']}")
            print(f"  origen={(t['origen'] or '')[:80]!r}")
        await orig.close()
        await dest.close()
        return 0

    # === EXECUTE ===
    t_start = time.time()
    async with httpx.AsyncClient() as client:

        # FASE 1 — Migrar nodos reales
        print(f"=== FASE 1 — migrar {n_nodos} nodos reales ===")
        node_id_map: dict[int, int] = {}
        nodos = await orig.fetch(
            "SELECT id, nombre, tipo, descripcion, created_at FROM nodos ORDER BY id"
        )
        for nodo in nodos:
            new_id = await dest.fetchval(
                """INSERT INTO nodes (name, type, description, created_at)
                   VALUES ($1, $2, $3, $4) RETURNING id""",
                nodo["nombre"], nodo["tipo"], nodo["descripcion"], nodo["created_at"],
            )
            node_id_map[nodo["id"]] = new_id
        print(f"  insertados: {len(node_id_map)} (en {time.time() - t_start:.1f}s)")

        # FASE 2 — Crear nodos artificiales tipo literal
        print(f"\n=== FASE 2 — crear nodos literales ===")
        literales_rows = await orig.fetch("""
            SELECT DISTINCT objeto_literal FROM tripletas
            WHERE objeto_literal IS NOT NULL AND objeto_id IS NULL
        """)
        literal_id_map: dict[str, int] = {}
        for lit in literales_rows:
            txt = lit["objeto_literal"]
            try:
                new_id = await dest.fetchval(
                    """INSERT INTO nodes (name, type, description) VALUES ($1, 'literal', NULL)
                       RETURNING id""", txt
                )
            except asyncpg.UniqueViolationError:
                # Por si el literal coincide con name de un nodo real existente
                existing = await dest.fetchval("SELECT id FROM nodes WHERE name = $1", txt)
                new_id = existing
            literal_id_map[txt] = new_id
        print(f"  literales unicos creados: {len(literal_id_map)}")

        # FASE 3 — Re-embed nodos en batches
        all_nodes = await dest.fetch("SELECT id, name, description FROM nodes ORDER BY id")
        print(f"\n=== FASE 3 — re-embed {len(all_nodes)} nodos (batches de {EMB_BATCH_SIZE}) ===")
        t_emb = time.time()
        for i in range(0, len(all_nodes), EMB_BATCH_SIZE):
            batch = all_nodes[i:i + EMB_BATCH_SIZE]
            texts = [
                f"{n['name']}. {n['description']}" if n["description"] else n["name"]
                for n in batch
            ]
            embeddings = await embed_batch(client, texts)
            for n, emb in zip(batch, embeddings):
                literal = vec_to_pgvector(emb)
                await dest.execute(
                    "UPDATE nodes SET embedding = $1::vector WHERE id = $2",
                    literal, n["id"],
                )
            if (i // EMB_BATCH_SIZE) % 20 == 0:
                print(f"  embedded {min(i + EMB_BATCH_SIZE, len(all_nodes))} / {len(all_nodes)} ({time.time() - t_emb:.1f}s)")
        print(f"  done en {time.time() - t_emb:.1f}s")

        # FASE 4 — Crear nodos AGE
        all_nodes_after_emb = await dest.fetch("SELECT id, name FROM nodes ORDER BY id")
        print(f"\n=== FASE 4 — crear {len(all_nodes_after_emb)} nodos AGE ===")
        t_age = time.time()
        for n in all_nodes_after_emb:
            await create_age_node(dest, n["name"], n["id"])
        print(f"  done en {time.time() - t_age:.1f}s")

        # FASE 5 — Migrar tripletas (con objeto_id real o literal)
        print(f"\n=== FASE 5 — migrar {n_tripletas} tripletas + aristas AGE ===")
        t_trip = time.time()
        tripletas = await orig.fetch("""
            SELECT id, sujeto_id, predicado, objeto_id, objeto_literal, autor,
                   peso, fecha, origen, created_at
            FROM tripletas ORDER BY id
        """)

        skipped = 0
        inserted_triples = 0
        author_count = {"explicit": 0, "migration": 0}

        for t in tripletas:
            # Resolver subject_id
            sujeto_old = t["sujeto_id"]
            if sujeto_old not in node_id_map:
                skipped += 1
                continue  # tripleta huerfana sin sujeto en mapping (no deberia pasar)
            subject_new = node_id_map[sujeto_old]

            # Resolver object_id (puede venir de objeto_id o de objeto_literal)
            object_new: Optional[int] = None
            if t["objeto_id"] is not None:
                object_new = node_id_map.get(t["objeto_id"])
            elif t["objeto_literal"] is not None:
                object_new = literal_id_map.get(t["objeto_literal"])

            if object_new is None:
                skipped += 1
                continue

            # Determinar author
            autor_orig = t["autor"]
            if autor_orig is None or autor_orig == "":
                author = MIGRATION_AUTHOR
                author_count["migration"] += 1
            else:
                author = autor_orig
                author_count["explicit"] += 1

            # Construir metadata
            metadata = {}
            if t["peso"] is not None and t["peso"] != 1.0:
                metadata["peso"] = float(t["peso"])
            metadata_json = json.dumps(metadata) if metadata else "{}"

            # INSERT en triples
            try:
                new_triple_id = await dest.fetchval(
                    """
                    INSERT INTO triples
                      (subject_id, predicate, object_id, author, fecha, origen, metadata, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
                    RETURNING id
                    """,
                    subject_new, t["predicado"], object_new, author,
                    t["fecha"], t["origen"], metadata_json, t["created_at"],
                )
            except asyncpg.UniqueViolationError:
                # Tripleta duplicada (mismo s, p, o ya existe). Skip silencioso.
                skipped += 1
                continue

            # Crear arista AGE
            await create_age_edge(dest, subject_new, object_new, t["predicado"], new_triple_id)
            inserted_triples += 1

            if inserted_triples % 500 == 0:
                print(f"  tripletas insertadas: {inserted_triples} ({time.time() - t_trip:.1f}s)")

        print(f"  tripletas insertadas: {inserted_triples} (skipped: {skipped}) en {time.time() - t_trip:.1f}s")
        print(f"  authors: explicit={author_count['explicit']} migration={author_count['migration']}")

        # FASE 6 — Re-embed predicados unicos
        print(f"\n=== FASE 6 — re-embed {n_predicados} predicados unicos ===")
        t_pred = time.time()
        preds = await orig.fetch("SELECT DISTINCT predicado FROM tripletas WHERE predicado IS NOT NULL")
        pred_list = [p["predicado"] for p in preds]
        for i in range(0, len(pred_list), EMB_BATCH_SIZE):
            batch = pred_list[i:i + EMB_BATCH_SIZE]
            embeddings = await embed_batch(client, batch)
            for predicate, emb in zip(batch, embeddings):
                literal = vec_to_pgvector(emb)
                try:
                    await dest.execute(
                        """INSERT INTO predicate_embeddings (predicate, embedding)
                           VALUES ($1, $2::vector)
                           ON CONFLICT (predicate) DO UPDATE SET
                             embedding = EXCLUDED.embedding, updated_at = now()""",
                        predicate, literal,
                    )
                except Exception as e:
                    print(f"  WARN predicado {predicate!r}: {e}")
            if (i // EMB_BATCH_SIZE) % 10 == 0:
                print(f"  embedded predicados {min(i + EMB_BATCH_SIZE, len(pred_list))} / {len(pred_list)} ({time.time() - t_pred:.1f}s)")
        print(f"  done en {time.time() - t_pred:.1f}s")

    # === Verificacion final ===
    print(f"\n=== VERIFICACION FINAL ===")
    n_nodes_final = await dest.fetchval("SELECT COUNT(*) FROM nodes")
    n_triples_final = await dest.fetchval("SELECT COUNT(*) FROM triples")
    n_pe_final = await dest.fetchval("SELECT COUNT(*) FROM predicate_embeddings")
    n_emb_null = await dest.fetchval("SELECT COUNT(*) FROM nodes WHERE embedding IS NULL")
    n_age_nodes_final = await dest.fetchrow(
        f"""SELECT * FROM cypher('{GRAPH_NAME}', $$ MATCH (n:Entity) RETURN COUNT(n) $$)
            AS (c agtype)"""
    )
    n_age_edges_final = await dest.fetchrow(
        f"""SELECT * FROM cypher('{GRAPH_NAME}', $$ MATCH ()-[r:RELATES_TO]->() RETURN COUNT(r) $$)
            AS (c agtype)"""
    )
    n_migration_author = await dest.fetchval(
        "SELECT COUNT(*) FROM triples WHERE author = $1", MIGRATION_AUTHOR
    )

    print(f"  nodes EcoDB: {n_nodes_final} (esperado {n_nodos + n_literales} = {n_nodos} + {n_literales})")
    print(f"  triples EcoDB: {n_triples_final} (esperado <= {n_tripletas}, skipped: {skipped})")
    print(f"  predicate_embeddings: {n_pe_final} (esperado {n_predicados})")
    print(f"  nodes con embedding: {n_nodes_final - n_emb_null} / {n_nodes_final} (NULL: {n_emb_null})")
    print(f"  AGE nodos :Entity: {str(n_age_nodes_final['c']).strip()}")
    print(f"  AGE aristas :RELATES_TO: {str(n_age_edges_final['c']).strip()}")
    print(f"  triples con author=MIGRATION: {n_migration_author} (esperado {n_autores_vacios - skipped if skipped < n_autores_vacios else 'aprox'})")
    print(f"\nTOTAL elapsed: {time.time() - t_start:.1f}s")

    await orig.close()
    await dest.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(dry_run=args.dry_run)))
