"""#717: fill the embedding of ACTIVE memories that have none (the cell wrote them with raw
SQL until ab7fcca+1; 97 on 23-oct). Idempotent: only rows WHERE embedding IS NULL are
touched, one UPDATE per row, guarded by the same condition, so a re-run or a concurrent
writer never overwrites a vector. Dry run by default: it lists and counts, writes nothing.

    python scripts/backfill_embeddings.py              # dry run: what would be filled
    python scripts/backfill_embeddings.py --apply      # fill them

Needs DATABASE_URL and EMBEDDINGS_URL (run it inside the api container: both are set there).
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

import asyncpg  # noqa: E402

from embeddings_client import embed_text  # noqa: E402


async def main(apply: bool) -> int:
    conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
    try:
        rows = await conn.fetch("""
            SELECT id, type, left(content, 60) AS head, content FROM memories
            WHERE embedding IS NULL AND staleness = 'active' AND content_type = 'text'
            ORDER BY created_at
        """)
        print(f"{len(rows)} active text memories without embedding")
        filled = failed = 0
        for r in rows:
            if not apply:
                print(f"  would fill {r['id']} [{r['type']}] {r['head']!r}")
                continue
            try:
                vec = await embed_text(r["content"], prompt_name="passage")
            except Exception as e:
                failed += 1
                print(f"  FAILED {r['id']}: {e}")
                continue
            done = await conn.execute(
                "UPDATE memories SET embedding = $2::vector WHERE id = $1 AND embedding IS NULL",
                r["id"], vec)
            filled += done.endswith(" 1")
        if apply:
            left = await conn.fetchval(
                "SELECT count(*) FROM memories WHERE embedding IS NULL AND staleness='active' "
                "AND content_type='text'")
            print(f"filled {filled}, failed {failed}, still without embedding: {left}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the embeddings (default: dry run)")
    sys.exit(asyncio.run(main(ap.parse_args().apply)))
