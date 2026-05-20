"""— Migracion retroactiva GLiNER + memory_entity_links.

Script one-shot que itera todas las memorias existentes y aplica GLiNER + linking
si la memoria NO tiene filas en memory_entity_links todavia (idempotente).

Uso:
    docker exec ecodb-api python /app/migrate_3_0c_entity_links.py [--dry-run]

Comportamiento:
- Por cada memoria:
  - Si memory_entity_links YA tiene filas → SKIP.
  - Si no → llama link_entities_from_content() en transaccion atomica.
  - Cualquier fallo individual NO aborta la migracion entera (try/except per row).
- Reporte final: skipped / linked / failed / total.

Decisiones tecnicas:
- Procesa en orden created_at ASC para que las migradas mas viejas se enriquezcan
  primero (semantica de "rebuild from scratch").
- Una conexion asyncpg compartida — lineal, sin paralelismo. Para 946 memorias y
  ~200-500ms por GLiNER call, esperado ~3-8 min.
- Idempotente: re-correr el script no duplica nada (gracias a ON CONFLICT en el
  helper + el SKIP previo).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

import asyncpg


async def migrate(dry_run: bool) -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    # Import del helper — requiere que el script corra dentro del container api
    # (donde gliner y todas las deps estan instaladas).
    from graph import link_entities_from_content

    conn = await asyncpg.connect(dsn=dsn)
    try:
        rows = await conn.fetch(
            """
            SELECT m.id, m.content
            FROM memories m
            WHERE NOT EXISTS (
                SELECT 1 FROM memory_entity_links mel WHERE mel.memory_id = m.id
            )
            ORDER BY m.created_at ASC
            """
        )
        total = len(rows)
        print(f"[3.0c] Memorias a procesar (sin entity_links): {total}")
        if dry_run:
            print("[3.0c] DRY RUN — no se hacen INSERTs.")
            return

        linked = 0
        failed = 0
        t_start = time.time()
        for i, row in enumerate(rows, 1):
            memory_id = row["id"]
            content = row["content"]
            try:
                async with conn.transaction():
                    count = await link_entities_from_content(conn, memory_id, content)
                if count > 0:
                    linked += 1
                # Si count == 0 (GLiNER no detecto entidades o fallo silencioso)
                # tambien lo contamos como "procesado sin error".
            except Exception as exc:
                failed += 1
                print(f"[3.0c] FAILED memory={memory_id}: {exc!r}", file=sys.stderr)

            if i % 50 == 0 or i == total:
                elapsed = time.time() - t_start
                rate = i / elapsed if elapsed > 0 else 0
                eta = (total - i) / rate if rate > 0 else 0
                print(
                    f"[3.0c] progreso {i}/{total} "
                    f"linked={linked} failed={failed} "
                    f"elapsed={elapsed:.1f}s eta={eta:.0f}s"
                )

        elapsed_total = time.time() - t_start
        print(
            f"\n[3.0c] CIERRE: total={total} linked={linked} failed={failed} "
            f"elapsed={elapsed_total:.1f}s"
        )
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo cuenta, no INSERT.")
    args = parser.parse_args()
    asyncio.run(migrate(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
