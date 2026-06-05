# Plan — EcoDB Installation Path Consolidation (v2)

## Metadatos
- **Proyecto**: C:\Users\Admin\Documents\EcoDB
- **Encargo de Pepe**: Spec+Plan unificado para consolidar install path de EcoDB
- **Nivel**: critical
- **Origen del Plan**: workflow-diseño v4, Loop 2 cerrado
- **Fecha**: 2026-06-05
- **Spec asociado**: consolidacion_v1_spec.md v2

## Resumen del trabajo

Consolidar el install path de EcoDB: migration runner idempotente para upgrades, fix de permisos de media, securización del broadcast secret, error sanitizado en dashboard, test de schema real, limpieza de version drift, y actualización de docs. 7 tasks, ~6-8h estimadas.

## Tasks

### Task 1: Migration runner

- **objetivo**: Crear el migration runner idempotente que aplica las 4 migraciones en cada boot de la API, cerrando el upgrade path roto.
- **archivos_a_tocar**:
  - `api/migrations.py` (NUEVO)
  - `api/main.py` (modificar lifespan)
  - `api/settings.py` (SCHEMA_VERSION)
  - `docker-compose.yml` (volume mount sql/)
- **accion**: |
  1. Crear `api/migrations.py` con la implementación EXACTA del Spec §3 — `run_migrations()` con `pg_advisory_lock` (session-level), sin `conn.transaction()` wrapper, logging por migración.
  2. En `api/main.py`, insertar después de `settings.validate_production_secrets()` y ANTES del bloque `try: load_dictionary_to_cache`:
     ```python
     from migrations import run_migrations
     pool = await get_pool()
     await run_migrations(pool)
     ```
  3. En `api/settings.py`, cambiar `SCHEMA_VERSION = "5.1.1"` (buscar `SCHEMA_VERSION = "5.1.0"`).
  4. En `docker-compose.yml`, añadir al servicio `api` en la sección `volumes:`:
     ```yaml
     - ./sql:/app/sql:ro
     ```
- **pre_condiciones**:
  - Los 4 archivos .sql existen en `sql/`
  - `api/db.py` exporta `get_pool()`
- **post_condiciones**:
  - API arranca y loguea 4 migraciones OK
  - `settings.SCHEMA_VERSION == "5.1.1"`
  - sql/ accesible en el container via volume mount
- **tests**:
  - `docker exec ecodb-api python -c "import migrations; print(migrations.MIGRATIONS)"` → lista de 4 tuplas
  - `docker exec ecodb-postgres psql -U ecodb -d ecodb -tAc "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"` → `5.1.1`
  - `docker logs ecodb-api 2>&1 | grep "ecodb.migrations"` → 4 líneas "migration OK"
  - `curl -s http://localhost:8080/health | python -c "import sys,json; print(json.load(sys.stdin).get('schema_version_target'))"` → `5.1.1`
  - **Test CE2 (upgrade path)**: levantar postgres aislado con solo init.sql (schema 5.0.0), arrancar API contra él, verificar que el runner aplica las 4 migraciones y el schema llega a 5.1.1. Procedimiento:
    ```bash
    docker run --name ecodb-upgrade-test -d -e POSTGRES_DB=ecodb -e POSTGRES_USER=ecodb -e POSTGRES_PASSWORD=test -p 5499:5432 postgres:17
    sleep 3
    docker exec -i ecodb-upgrade-test psql -U ecodb -d ecodb < sql/init.sql
    # Verificar baseline: debe ser 5.0.0
    docker exec ecodb-upgrade-test psql -U ecodb -d ecodb -tAc "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
    # Arrancar API apuntando al postgres de test (requiere DATABASE_URL override)
    # Verificar post-boot: debe ser 5.1.1
    docker rm -f ecodb-upgrade-test
    ```
- **criterio_de_exito**: Fresh install y upgrade path ambos producen schema 5.1.1 con 4 triggers AGE y todas las tablas/columnas presentes.
- **rollback**: `no_destructiva` — quitar las 3 líneas de main.py, eliminar migrations.py, quitar volume mount.
- **depende_de**: []

### Task 2: Docker entrypoint + media permissions

- **objetivo**: Resolver permisos del volumen media con entrypoint root + gosu.
- **archivos_a_tocar**:
  - `api/entrypoint.sh` (NUEVO)
  - `api/Dockerfile` (instalar gosu, añadir ENTRYPOINT, quitar USER apiuser)
- **accion**: |
  1. Crear `api/entrypoint.sh` con el contenido EXACTO del Spec §3.
  2. En `api/Dockerfile`:
     - Buscar la línea `apt-get install -y --no-install-recommends curl ffmpeg` → añadir `gosu` al final
     - Después del bloque de COPY de archivos .py, añadir:
       ```dockerfile
       COPY --chown=root:root entrypoint.sh /entrypoint.sh
       RUN chmod +x /entrypoint.sh
       ```
     - Buscar y eliminar la línea `USER apiuser` (está después del `RUN chown` de .cache)
     - Antes de la línea CMD, añadir:
       ```dockerfile
       ENTRYPOINT ["/entrypoint.sh"]
       ```
- **pre_condiciones**: Task 1 completada (Dockerfile ya tocado para otros cambios si los hubo)
- **post_condiciones**:
  - API corre como apiuser (via gosu)
  - Media directory writable por apiuser
- **tests**:
  - `docker exec ecodb-api whoami` → `apiuser`
  - `docker exec ecodb-api touch /app/media/test_write && echo OK` → `OK`
  - `docker exec ecodb-api rm /app/media/test_write`
  - `docker exec ecodb-api gosu --version` → exits 0
- **criterio_de_exito**: `docker compose up -d` desde cero → media uploads funcionan sin intervención manual.
- **rollback**: Restaurar `USER apiuser`, eliminar ENTRYPOINT y entrypoint.sh, quitar gosu.
- **depende_de**: [Task 1]

### Task 3: INTERNAL_BROADCAST_SECRET security

- **objetivo**: Eliminar el secreto público, generar uno único por instalación, y validar en producción.
- **archivos_a_tocar**:
  - `docker-compose.yml` (quitar default en 2 líneas)
  - `.env.example` (añadir variable)
  - `scripts/setup.sh` (generar secreto + quitar ECODB_SEED_DEMO)
  - `scripts/setup.ps1` (generar secreto + quitar ECODB_SEED_DEMO)
  - `api/settings.py` (validación WARNING)
- **accion**: |
  1. En `docker-compose.yml`, buscar las 2 ocurrencias de `INTERNAL_BROADCAST_SECRET: ${INTERNAL_BROADCAST_SECRET:-fa8b0c02...}` → cambiar a `INTERNAL_BROADCAST_SECRET: ${INTERNAL_BROADCAST_SECRET}`
  2. En `.env.example`, añadir sección Internal broadcast (ver Spec §3).
  3. En `scripts/setup.sh`:
     - Añadir check + generación (ver Spec §3 — comprobar `grep -q` antes de append)
     - Buscar y eliminar la línea que escribe `ECODB_SEED_DEMO`
  4. En `scripts/setup.ps1`:
     - Añadir check + generación PowerShell (ver Spec §3 — comprobar `Select-String` antes)
     - Buscar y eliminar la línea que escribe `ECODB_SEED_DEMO`
  5. En `api/settings.py`, al final de `validate_production_secrets()`, añadir WARNING (ver Spec §3).
- **pre_condiciones**: []
- **post_condiciones**:
  - Sin default hardcodeado en compose
  - .env.example documenta la variable
  - Setup scripts generan secreto único
  - Producción sin secreto loguea WARNING
- **tests**:
  - `grep -c "fa8b0c02" docker-compose.yml` → `0`
  - `grep "INTERNAL_BROADCAST_SECRET" .env.example` → match
  - `grep "ECODB_SEED_DEMO" scripts/setup.sh` → no match
  - `grep "ECODB_SEED_DEMO" scripts/setup.ps1` → no match
- **criterio_de_exito**: Nuevo install via setup genera secreto único. Compose sin default público.
- **rollback**: `no_destructiva`
- **depende_de**: []

### Task 4: Dashboard error sanitization (CONN-2)

- **objetivo**: Mostrar mensaje útil en errores 500 sin exponer información interna.
- **archivos_a_tocar**:
  - `dashboard/src/lib/errMsg.ts`
  - `dashboard/src/locales/en.json`
  - `dashboard/src/__tests__/errMsg.test.ts`
- **accion**: |
  1. En `errMsg.ts`, dentro del bloque `if (err instanceof ApiError)`, ANTES del cierre `}`, añadir el case 5xx (ver Spec §3).
  2. En `en.json`, añadir key `serverError`.
  3. En `errMsg.test.ts`, añadir test para status 500 → espera `"Server error (500). Check server logs for details."`
- **pre_condiciones**: []
- **post_condiciones**:
  - 500 → mensaje sanitizado
  - 422 → field detail (no regresión)
  - Test nuevo pasa
- **tests**:
  - `grep "serverError" dashboard/src/locales/en.json` → match
  - `grep "err.status >= 500" dashboard/src/lib/errMsg.ts` → match
  - `cd dashboard && npm test -- --grep "500"` → PASS
- **criterio_de_exito**: 500 muestra mensaje accionable, no "Couldn't reach EcoDB".
- **rollback**: `no_destructiva`
- **depende_de**: []

### Task 5: Schema version test

- **objetivo**: Test de integración que detecte drift entre settings.SCHEMA_VERSION y la DB real.
- **archivos_a_tocar**:
  - `tests/test_health.py`
- **accion**: |
  1. Añadir test `test_schema_version_matches_db`:
     - Conecta a postgres via `settings.DATABASE_URL`
     - Ejecuta `SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1`
     - Compara con `settings.SCHEMA_VERSION`
     - Assert igualdad
  2. Marcar con skip si postgres no disponible (connection error → pytest.skip)
- **pre_condiciones**: Task 1 completada (SCHEMA_VERSION corregido)
- **post_condiciones**: Test pasa con postgres, se skipea sin postgres
- **tests**:
  - `pytest tests/test_health.py -k schema_version_db -v` → PASSED (con postgres)
  - Sin postgres: → SKIPPED
- **criterio_de_exito**: El test detectaría un drift como V1.
- **rollback**: `no_destructiva`
- **depende_de**: [Task 1]

### Task 6: Settings + version drift cleanup

- **objetivo**: Limpiar los items de version drift (V3, V4, V7, V8, V10, D14).
- **archivos_a_tocar**:
  - `api/settings.py` (V7 CORS, V8 docstring, D14 ENVIRONMENT) — verificar si Task 1/3 ya los tocaron
  - `mcp/server.py` (V3: docstring "31-tool" → "32-tool")
  - `dashboard/src/pages/Settings.tsx` (V4: quitar tag "v0.9")
  - `CLAUDE.md` (V10: release version → v1.1.1)
- **accion**: |
  1. `mcp/server.py`: buscar "31-tool" → cambiar a "32-tool"
  2. `dashboard/src/pages/Settings.tsx`: buscar "v0.9" como tag hardcodeado → eliminar
  3. `CLAUDE.md`: buscar "Release pública:" → cambiar a "v1.1.1"
  4. `settings.py`: verificar que CORS default ya es "8080,8091" (si no, cambiar)
  5. `settings.py`: verificar que docstring API_VERSION dice "0.9.0" (si no, corregir)
  6. `settings.py`: verificar que ENVIRONMENT default es "development" (si no, cambiar)
- **pre_condiciones**: []
- **post_condiciones**: Todos los V-items correctos
- **tests**:
  - `grep "31-tool" mcp/server.py` → no match
  - `grep '"v0.9"' dashboard/src/pages/Settings.tsx` → no match
  - `grep "v0.9.5" CLAUDE.md | grep -i release` → no match
  - `grep "8081" api/settings.py` → no match
- **criterio_de_exito**: Cada V-item verificado con grep negativo.
- **rollback**: `no_destructiva`
- **depende_de**: []

### Task 7: Documentation updates

- **objetivo**: README con env vars, CHANGELOG al día, convención de migraciones documentada.
- **archivos_a_tocar**:
  - `README.md`
  - `CHANGELOG.md`
  - `CLAUDE.md` (convención de migraciones)
- **accion**: |
  1. `README.md`:
     - Añadir sección "## Environment Variables" con tabla de vars clave
     - Corregir clone URL si usa `ecodb` minúscula → `EcoDB`
     - Añadir comando de verificación de schema version
     - Enlazar migration guides faltantes
     - Nota sobre GGUF para with-llm profile
  2. `CHANGELOG.md`:
     - Añadir entradas para 0.9.5, 1.0.0, 1.1.0, 1.1.1 (basarse en CLAUDE.md + git log)
  3. `CLAUDE.md`:
     - Añadir sección "Migration convention": nuevas migraciones se añaden al final de `MIGRATIONS` en `api/migrations.py`, deben ser idempotentes (IF NOT EXISTS / OR REPLACE / ON CONFLICT DO NOTHING), con BEGIN/COMMIT propio si necesitan atomicidad.
- **pre_condiciones**: []
- **post_condiciones**: README y CHANGELOG actualizados, convención documentada
- **tests**:
  - `grep "Environment Variables" README.md` → match
  - `grep "1.1.1" CHANGELOG.md` → match
  - `grep "0.9.5" CHANGELOG.md` → match
  - `grep -i "migration convention" CLAUDE.md` → match
- **criterio_de_exito**: Usuario que lea README entiende las variables. CHANGELOG tiene historial completo. Contribuidor sabe cómo añadir migraciones.
- **rollback**: `no_destructiva`
- **depende_de**: []

---

## Notas

- Tasks 1-2 son secuenciales (Task 2 depende de Task 1 por tocar el mismo Dockerfile).
- Task 5 depende de Task 1 (necesita SCHEMA_VERSION corregido).
- Tasks 3, 4, 6, 7 son independientes entre sí y del resto.
- Ninguna task es destructiva — todas tienen rollback trivial.
- Los tests deben ejecutarse tal cual contra un docker compose levantado.
- El test de CE2 (upgrade path) en Task 1 requiere un postgres aislado temporal.
