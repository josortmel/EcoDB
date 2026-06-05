# Brief — EcoDB Installation Path Consolidation (v2)

## Metadatos
- **Proyecto**: C:\Users\Admin\Documents\EcoDB
- **Fecha**: 2026-06-05
- **Versión**: v2 (post Loop 1 adversarial — 14 fixes applied from 24 observations)
- **Nivel**: critical
- **Encargo de Pepe (literal)**: "el otro dia Hilo realizo una pequeña auditoria de C:\Users\Admin\Documents\EcoDB para encontrar fallos y problemas que dificulten la instalacion [...] implementar un plan+spec unificado que Hilo pueda usar para continuar el trabajo de EcoDB"

---

## 1. Contexto y motivación

- **Qué problema resuelve**: TheRed699 (usuario externo) hizo un fresh install de EcoDB v1.0 y obtuvo errores 500 en todas las tools. La causa raíz: el schema nace en 5.0.0 pero el código espera 5.1.1. v1.1.1 parcheó el fresh install (initdb.d), pero el **upgrade path** sigue roto: initdb.d no re-corre en volúmenes existentes. Además, la auditoría reveló 50+ findings secundarios en seguridad, infra, dashboard y docs.
- **Por qué ahora**: EcoDB v1.0 es pública en GitHub. Cada día sin migration runner es un día donde un usuario que actualiza se encuentra con un schema roto. El broadcast secret público en GitHub es un riesgo activo.
- **Usuarios afectados**: Usuarios externos que instalan/actualizan EcoDB, Pepe (mantenedor), Hilo (ejecutor).

## 2. Decisiones de diseño (con trazabilidad)

- **D1**: Migration runner en el lifespan de la API, después de `validate_production_secrets()` (main.py:71) y antes del dictionary cache (main.py:91). Fail-fast con **logging estructurado**: logger `ecodb.migrations`, INFO por migración aplicada con nombre y duración, ERROR con nombre de migración y excepción completa si falla. El operador ve exactamente qué migración falló y por qué.
  - Origen: [audit §8.1] verificado contra `main.py:68-103` — `get_pool()` se invoca en main.py:93 (dictionary cache), DESPUÉS del punto de inserción del runner. El runner llama `get_pool()` él mismo.
  - Trade-off: API no arranca si falla. Mejor que servir con schema roto. El log detallado evita el antipatrón TheRed699 (fallo sin diagnóstico).
  - Alternativas descartadas: init-container (complejidad Docker), entrypoint postgres (mezcla responsabilidades)

- **D2**: Aplicar las 4 migraciones idempotentes en cada boot, sin tabla de tracking. Cada migración envuelta en `async with conn.transaction():` para atomicidad — si falla a mitad, rollback completo del archivo. Archivos de migración que tengan sus propios BEGIN/COMMIT funcionan con nested transaction (PG emite WARNING pero es correcto).
  - Origen: [audit §8.5] + [adversarial S1/S2 — atomicidad requerida]
  - Razón: 4 archivos idempotentes, coste bajo (CREATE IF NOT EXISTS en tablas vacías o existentes).
  - Trade-off: sin tracking table → re-aplica siempre. Aceptable a esta escala.

- **D3**: Lista explícita ordenada en código (`migrations.py`), no auto-descubrimiento.
  - Origen: [audit §8.5]
  - Razón: nombres no ordenables alfabéticamente.

- **D4**: `pg_advisory_xact_lock` (transaction-level) para concurrencia, NO `pg_advisory_lock` (session-level).
  - Origen: [audit §8.1/§8.6] + [adversarial A3 — session-level lock puede deadlock en crash-restart si unlock falla]
  - Razón: `pg_advisory_xact_lock` se libera automáticamente al terminar la transacción o al cerrar la conexión. Sin riesgo de lock huérfano. Clave constante arbitraria.
  - Alternativas descartadas: `pg_advisory_lock` con timeout (más complejo, mismo resultado)

- **D5**: Añadir `COPY --chown=apiuser:apiuser sql/ ./sql/` a `Dockerfile.api`, DESPUÉS de la línea `USER apiuser` (línea 40) o ANTES con --chown explícito.
  - Origen: [audit §8.2] — recomendaba explícitamente `--chown=apiuser:apiuser`
  - Razón: sin --chown, archivos owned por root → apiuser no puede leer → runner falla
  - [adversarial deepseek A1 BLOCKER corregido]

- **D6**: Mantener ambos mecanismos: initdb.d (fresh install) + runner (upgrades). **No es doble cobertura en ambos escenarios** — initdb.d solo corre en volumen vacío, runner solo es relevante en volumen poblado. Son complementarios, no redundantes.
  - Origen: [audit §8.7] + [adversarial deepseek C1 — clarificación de framing]

- **D7**: Corregir `SCHEMA_VERSION` a `"5.1.1"` en `settings.py:23`.
  - Origen: [audit V1]

- **D8**: Test de schema que compare `settings.SCHEMA_VERSION` contra la DB real. Query: `SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1`. Este es un test de integración (requiere postgres) — documentar requisito de entorno.
  - Origen: [audit V2] + [adversarial A1 BLOCKER — `current_setting()` incorrecto, schema_version es una TABLE no un GUC]

- **D9**: Generar `INTERNAL_BROADCAST_SECRET` en `setup.sh`/`setup.ps1`, añadirlo a `.env.example`, eliminar literal del compose. **Además**: añadir validación en `validate_production_secrets()` como WARNING (no hard failure) cuando ausente en production — API arranca pero loguea WARNING claro de que eventos del worker se perderán.
  - Origen: [audit B4/V6] + [adversarial C3 — silent data loss si ausente]

- **D10**: Resolver permisos del volumen media con **entrypoint script** que corre como root, hace `chown apiuser:apiuser /app/media`, y luego `exec gosu apiuser "$@"` para lanzar uvicorn como non-root. Patrón estándar Docker para named volumes.
  - Origen: [audit B5] + [adversarial A2 — USER apiuser en Dockerfile impide chown directo]
  - Cambios: nuevo `entrypoint.sh`, modificar Dockerfile.api (ENTRYPOINT antes de CMD, USER apiuser eliminado — gosu lo maneja), instalar gosu en el build stage
  - Trade-off: añade dependencia (gosu) pero es el patrón canónico para este problema

- **D11**: Dashboard: error 500 muestra **mensaje sanitizado**, nunca raw exception. Formato: `"Server error (500): <categoría genérica>. Check server logs for details."`. No stack traces, no SQL, no paths internos. El detalle real va al log del backend.
  - Origen: [audit CONN-2] + [adversarial A5 — decisión de seguridad requerida]

- **D12**: Limpieza de version drift: V3, V4, V5, V7, V8, V10.
  - Origen: [audit §9]

- **D13**: Docs: README (D2, D4/D6), CHANGELOG (D3).
  - Origen: [audit §4.D]

- **D14**: Cambiar default de `ENVIRONMENT` en `settings.py:18` de `"production"` a `"development"`.
  - Origen: [audit B8] + [adversarial deepseek C2 — sin decisión asociada en Brief v1]
  - Razón: `validate_production_secrets()` aborta en local sin export. El default "production" es un footgun para desarrollo.

---

## 3. Scope

### Dentro del scope
- Migration runner idempotente con atomicidad por transacción (D1-D6)
- Fix SCHEMA_VERSION + test real contra DB (D7-D8)
- Seguridad: INTERNAL_BROADCAST_SECRET generación + validación WARNING (D9)
- Infra: media permissions con entrypoint/gosu (D10), ENVIRONMENT default (D14)
- Dashboard: error 500 sanitizado (D11)
- Version drift cleanup (D12)
- Documentación (D13)

### Fuera del scope (deuda consciente)
- **INS-1**: Firma de código del instalador — decisión de coste
- **INS-2**: Auto-update con electron-updater
- **CI/CD**: GitHub Actions — el test de schema se escribe local
- **CONN-3**: FirstRun con chequeos reales
- **CONN-5**: URL editable pre-auth
- **B6**: Embeddings start_period — diferido (no cosmético; severidad MEDIUM del audit correcta). Trigger: primer usuario en conexión lenta que reporte timeout de arranque
- **B10**: worker depends_on api — best-effort, perfil with-ingestion
- CONN-1/4/6/7/8/9, V11, V12

---

## 4. Criterios de éxito (verificables)

- **CE1**: Fresh install → `SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1` devuelve `"5.1.1"`. Tablas: `memory_embeddings`, `graph_clusters` existen. Columnas: `nodes.name_canonical`, `api_keys.grace_until` existen. 4 triggers AGE presentes (`SELECT COUNT(*) FROM pg_trigger WHERE tgname LIKE 'trg_age_sync%'` = 4).
- **CE2**: Upgrade desde 5.0.0 → arrancar API con postgres que solo tiene init.sql aplicado, verificar schema post-boot = 5.1.1. Comando: `docker run --rm -e POSTGRES_DB=ecodb ... postgres:17`, aplicar solo init.sql, luego arrancar API contra ese postgres → runner aplica las 4 migraciones.
- **CE3**: `/health` reporta `schema_version_target: "5.1.1"`.
- **CE4**: `grep -c "fa8b0c02" docker-compose.yml` → 0. `INTERNAL_BROADCAST_SECRET` sin default hardcodeado.
- **CE5**: Media uploads sin chown manual: `docker compose up -d` → POST /memories con image → 200.
- **CE6**: Dashboard muestra mensaje sanitizado en 500: "Server error (500): ... Check server logs." Sin stack traces ni SQL.
- **CE7**: `pytest tests/test_health.py -k schema_version_db` compara settings vs DB real (requiere postgres).
- **CE8**: `grep "ECODB_SEED_DEMO" scripts/setup.sh scripts/setup.ps1` → 0 resultados (V5 limpio).
- **CE9**: `grep "31-tool" mcp/server.py` → 0 (V3). Settings.tsx sin tag "v0.9" hardcodeado (V4). CLAUDE.md dice v1.1.1 (V10). settings.py docstrings correctos (V7, V8).
- **CE10**: README tiene sección env vars. CHANGELOG tiene entradas 0.9.5/1.0.0/1.1.0/1.1.1.

---

## 5. Deuda explícita

- **DD1**: Tabla `schema_migrations` — trigger: primera migración no idempotente
- **DD2**: CI/CD con GitHub Actions — trigger: flujo de releases automatizado
- **DD3**: Firma de código (INS-1) — trigger: primer usuario no-técnico bloqueado por SmartScreen
- **DD4**: Auto-update (INS-2) — trigger: >10 usuarios activos del dashboard
- **DD5**: FirstRun con chequeos reales (CONN-3) — trigger: feedback post-CONN-2
- **DD6**: Convención documentada para añadir migraciones — trigger: cuando runner esté construido, documentar en CLAUDE.md
- **DD7**: Profiling del runner bajo carga — trigger: orquestación multi-réplica (k8s)
- **DD8**: Política de deprecación de migraciones — trigger: >10 migraciones

---

## 6. Preguntas resueltas (eran §6 del Brief v1)

- **Atomicidad multi-statement**: resuelto con `async with conn.transaction():` por migración (D2). Archivos con BEGIN/COMMIT propio funcionan como nested tx.
- **¿Runner debe verificar schema_version antes de aplicar?**: no — idempotente, re-aplicar es no-op.
- **¿Cómo testear upgrade sin CI?**: CE2 con postgres aislado vía docker run.
- **¿Entrypoint rompe deployments existentes?**: no — gosu es transparent, CMD no cambia.
- **¿500 filtra info sensible?**: resuelto con sanitización (D11). Status code + categoría genérica.
- **¿Orden incorrecto en migrations.py?**: lista explícita en código, no auto-descubrimiento (D3).

---

## Referencias

- Auditoría de Hilo: `Eco_Consulting/Faro/Informes/Diseño/EcoDB/2026-06-03_EcoDB_auditoria_instalacion_findings.md`
- Adversarial Sonnet (Loop 1): `EcoDB/.faro/reportes_diseno/adversarial_report.md`
- Adversarial DeepSeek (Loop 1): `EcoDB/.faro/reportes_diseno/adversarial_deepseek_report.md`
- Verificación de estado actual: `settings.py:23`, `main.py:68-103`, `api/Dockerfile:31-40`, `docker-compose.yml:34-43`, `init.sql:46-50`
