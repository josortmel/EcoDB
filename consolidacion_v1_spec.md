# Spec — EcoDB Installation Path Consolidation (v2)

## Metadatos
- **Proyecto**: C:\Users\Admin\Documents\EcoDB
- **Fecha**: 2026-06-05
- **Versión**: v2 (post Loop 2 adversarial — 12 fixes applied from 17 observations)
- **Brief de referencia**: consolidacion_v1_brief.md v2
- **verification_checkpoint de referencia**: verification_checkpoint.md (2026-06-05 12:15 CET)

---

## 1. Cita a Brief y verification_checkpoint

- Este Spec implementa las decisiones D1-D14 del Brief v2.
- Está alineado con la realidad capturada en verification_checkpoint.md (H1-H8).

### Drift consciente
- **Drift 1**: Brief D5 dice `COPY --chown=apiuser:apiuser sql/ ./sql/` en Dockerfile.api. Spec usa **volume mount** `./sql:/app/sql:ro` en docker-compose.yml. Razón: el build context de la imagen api es `./api` (docker-compose.yml:95). `sql/` está en la raíz del proyecto, fuera del build context. COPY falla. El volume mount es la solución más limpia sin reestructurar el build context.
- **Drift 2**: Brief D4 dice `pg_advisory_xact_lock` (transaction-level). Spec usa **`pg_advisory_lock`** (session-level) con unlock explícito en finally. Razón: 3 de 4 archivos .sql tienen BEGIN/COMMIT propio. `conn.transaction()` de asyncpg + COMMIT en el SQL termina la transacción exterior, rompiendo el savepoint. Sin transaction wrapper, `pg_advisory_xact_lock` no funciona (requiere transacción activa). Session-level lock con finally es la propuesta original de la auditoría §8.6.

---

## 2. Schema / DDL

No aplica — las migraciones existentes se re-aplican tal cual. No se crean tablas ni columnas nuevas.

---

## 3. Signatures de funciones / módulos nuevos

### `api/migrations.py` (nuevo)

```python
"""Idempotent migration runner for EcoDB.

Applies pending SQL migrations on every API startup. All migrations
are idempotent (IF NOT EXISTS / OR REPLACE / ON CONFLICT DO NOTHING),
so re-applying is a no-op on an up-to-date schema.

Runs inside the FastAPI lifespan, after validate_production_secrets()
and before the dictionary cache. Uses pg_advisory_lock to serialize
concurrent startups (future multi-replica).
"""
import logging
import time
from pathlib import Path

import settings

log = logging.getLogger("ecodb.migrations")

MIGRATIONS: list[tuple[str, str]] = [
    ("3_0h_multimodal",   "sql/migrate_3_0h_multimodal.sql"),
    ("5.1.0_multitenant", "sql/migrate_5.0.1_to_5.1.0.sql"),
    ("5.1.1_clusters",    "sql/migrate_5.1.0_to_5.1.1.sql"),
    ("age_sync_triggers", "sql/trigger_age_sync.sql"),
]

_LOCK_KEY = 728_1990


async def run_migrations(pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock($1)", _LOCK_KEY)
        try:
            for name, path in MIGRATIONS:
                sql = Path(path).read_text(encoding="utf-8")
                t0 = time.monotonic()
                await conn.execute(sql)
                elapsed = (time.monotonic() - t0) * 1000
                log.info("migration OK: %s (%.0f ms)", name, elapsed)
            log.info("schema at target %s", settings.SCHEMA_VERSION)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _LOCK_KEY)
```

**Notas**:
- Sin `conn.transaction()` wrapper — 3/4 archivos tienen BEGIN/COMMIT propio. El wrapper rompe asyncpg savepoints.
- `pg_advisory_lock` es session-level. Se libera en finally o cuando la conexión cierra (crash).
- `Path(path)` resuelve relativo a `/app` (workdir del contenedor). `sql/` accesible via volume mount.

### `api/entrypoint.sh` (nuevo)

```bash
#!/bin/sh
set -e
if [ -d /app/media ] && [ "$(stat -c %u /app/media)" != "1000" ]; then
    chown -R apiuser:apiuser /app/media
fi
exec gosu apiuser "$@"
```

### Cambios en `api/Dockerfile`

```dockerfile
# Línea 10: añadir gosu al apt-get install
RUN ... apt-get install -y --no-install-recommends curl ffmpeg gosu ...

# Después de COPY de .py files y chown .cache:
COPY --chown=root:root entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ELIMINAR: USER apiuser (gosu lo maneja)

# AÑADIR antes del CMD:
ENTRYPOINT ["/entrypoint.sh"]

# CMD sin cambios
```

**NO añadir COPY sql/**: accesible via volume mount en docker-compose.yml.

### Cambios en `docker-compose.yml`

```yaml
# Servicio api — añadir volume:
volumes:
  - ./sql:/app/sql:ro

# Líneas con INTERNAL_BROADCAST_SECRET (api y worker): quitar default
INTERNAL_BROADCAST_SECRET: ${INTERNAL_BROADCAST_SECRET}
```

### Cambios en `api/main.py` — lifespan

Insertar después de `settings.validate_production_secrets()` y ANTES del bloque `try: load_dictionary_to_cache`:

```python
from migrations import run_migrations
pool = await get_pool()
await run_migrations(pool)
```

### Cambios en `api/settings.py`

```python
# Default ENVIRONMENT: "production" → "development"
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

# SCHEMA_VERSION: "5.1.0" → "5.1.1"
SCHEMA_VERSION = "5.1.1"

# Docstring API_VERSION: corregir a "0.9.0"
# CORS default: "8080,8081" → "8080,8091"
_default_origins = "http://localhost:8080,http://localhost:8091"

# Al final de validate_production_secrets(), añadir:
    _broadcast_secret = os.environ.get("INTERNAL_BROADCAST_SECRET", "")
    if not _broadcast_secret or len(_broadcast_secret) < 16:
        import logging
        logging.getLogger("ecodb.security").warning(
            "INTERNAL_BROADCAST_SECRET empty or too short in production. "
            "Worker SSE events will be silently dropped. "
            "Generate with: openssl rand -hex 32"
        )
```

### Cambios en `dashboard/src/lib/errMsg.ts`

Dentro del bloque `if (err instanceof ApiError)`, ANTES del cierre `}` (línea 34):

```typescript
    if (err.status >= 500) {
      return t('errors.serverError', { status: err.status });
    }
```

En `dashboard/src/locales/en.json`:
```json
"serverError": "Server error ({{status}}). Check server logs for details."
```

### Cambios en `.env.example`

Añadir después de la sección Auth secrets:
```
# ─── Internal broadcast ────────────────────────────────────────────
# Required for document ingestion events (with-ingestion profile).
# Without it, worker events are silently dropped.
# Generate with: openssl rand -hex 32
INTERNAL_BROADCAST_SECRET=<generated-by-setup.sh>
```

### Cambios en `scripts/setup.sh`

```bash
# Generar INTERNAL_BROADCAST_SECRET (comprobar que no exista ya)
if ! grep -q "INTERNAL_BROADCAST_SECRET" .env 2>/dev/null; then
    BROADCAST_SECRET=$(openssl rand -hex 32)
    echo "INTERNAL_BROADCAST_SECRET=$BROADCAST_SECRET" >> .env
fi

# ELIMINAR línea que escribe ECODB_SEED_DEMO
```

### Cambios en `scripts/setup.ps1`

```powershell
# Generar INTERNAL_BROADCAST_SECRET (comprobar que no exista ya)
if (-not (Select-String -Path .env -Pattern "INTERNAL_BROADCAST_SECRET" -Quiet -ErrorAction SilentlyContinue)) {
    $broadcastSecret = -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
    Add-Content -Path .env -Value "INTERNAL_BROADCAST_SECRET=$broadcastSecret" -Encoding utf8
}

# ELIMINAR línea ECODB_SEED_DEMO
```

---

## 4. Ejemplos reales

### Ejemplo 1: Fresh install — runner es no-op
```
INFO:ecodb.migrations:migration OK: 3_0h_multimodal (2 ms)
INFO:ecodb.migrations:migration OK: 5.1.0_multitenant (3 ms)
INFO:ecodb.migrations:migration OK: 5.1.1_clusters (1 ms)
INFO:ecodb.migrations:migration OK: age_sync_triggers (1 ms)
INFO:ecodb.migrations:schema at target 5.1.1
```

### Ejemplo 2: Upgrade desde 5.0.0
```
INFO:ecodb.migrations:migration OK: 3_0h_multimodal (45 ms)
INFO:ecodb.migrations:migration OK: 5.1.0_multitenant (120 ms)
INFO:ecodb.migrations:migration OK: 5.1.1_clusters (8 ms)
INFO:ecodb.migrations:migration OK: age_sync_triggers (15 ms)
INFO:ecodb.migrations:schema at target 5.1.1
```

### Ejemplo 3: Migration failure
```
ERROR:ecodb.migrations:migration FAILED: 5.1.0_multitenant
Traceback (most recent call last):
  ...
asyncpg.exceptions.InsufficientPrivilegeError: permission denied for table users
```
API no arranca. Operador ve exactamente qué migración falló.

---

## 5. Dependencias externas

| Dependencia | Versión | Nota |
|---|---|---|
| gosu | latest (apt) | Lightweight su for Docker entrypoints |
| asyncpg | (existing) | Pool.acquire(), conn.execute() |

---

## 6. Handling de errores

### `run_migrations(pool)`
- **Migration SQL fails** → `log.error` con nombre + traceback → `raise` → API no arranca
- **Connection lost** → `pool.acquire()` falla → `raise` → API no arranca
- **Lock contention** → `pg_advisory_lock` bloquea hasta que el lock se libere. Single worker, contención transitoria.
- **sql/ files missing** → `FileNotFoundError` → API no arranca con error claro

### `validate_production_secrets()` — INTERNAL_BROADCAST_SECRET
- **Empty/short** → WARNING, API continúa. Eventos perdidos pero API funcional.

### Dashboard errMsg
- **5xx** → "Server error (500). Check server logs." Nunca raw exception.
- **Network error** → fallback existente (genuinamente unreachable).

---

## 7. Criterios de éxito por componente

### Migration runner
- [ ] Fresh: schema 5.1.1, memory_embeddings/graph_clusters/name_canonical/grace_until existen, 4 triggers AGE
- [ ] Upgrade: postgres con solo init.sql → API boot → schema 5.1.1
- [ ] `/health` → schema_version_target: "5.1.1"
- [ ] Logs: 4 "migration OK" con tiempos

### Docker entrypoint
- [ ] Media uploads sin chown manual
- [ ] `docker exec ecodb-api whoami` = apiuser
- [ ] gosu instalado

### INTERNAL_BROADCAST_SECRET
- [ ] `grep "fa8b0c02" docker-compose.yml` = 0
- [ ] `.env.example` tiene INTERNAL_BROADCAST_SECRET
- [ ] Production sin secreto → WARNING en logs

### Dashboard
- [ ] 500 → "Server error (500). Check server logs."
- [ ] 422 → field detail (no regresión)
- [ ] Test unitario nuevo para 5xx case

### Schema test
- [ ] `pytest -k schema_version_db` PASS con postgres
- [ ] SKIP sin postgres

### Version drift
- [ ] ECODB_SEED_DEMO eliminado de ambos scripts
- [ ] mcp/server.py: "32-tool"
- [ ] Settings.tsx: sin "v0.9"
- [ ] CLAUDE.md: v1.1.1

### Docs
- [ ] README: sección env vars
- [ ] CHANGELOG: 4 entries nuevas
- [ ] Convención de migraciones documentada en CLAUDE.md
