"""Bootstrap script — crea la PRIMERA API key del sistema (out-of-band).

Uso:
    python bootstrap_first_apikey.py --user-id=1 --name="hilo-orquestador"

Conecta directo a la DB con DATABASE_URL del entorno y crea una API key activa
para el user indicado. Imprime la API key plain UNA vez y nunca mas.

NO usar este script tras el bootstrap inicial — para crear nuevas keys, usar
POST /auth/api-keys del API.

Variables de entorno necesarias:
- DATABASE_URL  : DSN postgres (default: localhost:5435 ecodb_test_pass).
- API_KEY_PEPPER: pepper compartido con el API (debe coincidir).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import asyncpg

import settings
from auth import generate_api_key


async def main(user_id: int, name: str) -> int:
    conn = await asyncpg.connect(dsn=settings.DATABASE_URL)
    try:
        target = await conn.fetchrow(
            "SELECT id, name, active FROM users WHERE id = $1", user_id
        )
        if target is None:
            print(f"[bootstrap] ERROR: user_id={user_id} no existe", file=sys.stderr)
            return 2
        if not target["active"]:
            print(f"[bootstrap] ERROR: user_id={user_id} esta inactivo", file=sys.stderr)
            return 2

        existing = await conn.fetchval(
            "SELECT count(*) FROM api_keys WHERE user_id = $1 AND active = true",
            user_id,
        )
        if existing > 0:
            print(
                f"[bootstrap] WARN: user_id={user_id} ya tiene {existing} API key(s) "
                f"activa(s). Continuando — esta script NO es idempotente, cada llamada "
                f"crea una key nueva.",
                file=sys.stderr,
            )

        key_plain, key_hash = generate_api_key()
        row = await conn.fetchrow(
            """
            INSERT INTO api_keys (key_hash, name, user_id, active)
            VALUES ($1, $2, $3, true)
            RETURNING id
            """,
            key_hash, name, user_id,
        )

        print()
        print("=" * 60)
        print(f" API KEY CREADA — id={row['id']}, user='{target['name']}', name='{name}'")
        print("=" * 60)
        print()
        print(f"  {key_plain}")
        print()
        print("=" * 60)
        print(" Guardala AHORA. No se vuelve a mostrar.")
        print(" Para crear mas keys: POST /auth/api-keys (requiere super o CEO).")
        print("=" * 60)
        print()
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True, help="ID del user destino")
    parser.add_argument("--name", type=str, required=True, help="Nombre legible de la key")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.user_id, args.name)))
