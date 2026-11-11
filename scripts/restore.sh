#!/usr/bin/env bash
# EcoDB restore — Tarea 1.13 plan maestro v3 §6.3 + §8 Fase 1.
# Restaura un dump de pg_dump (custom, o el .sql.gz plano de scripts/backup.sh) a una DB
# temporal y verifica integridad. Uso defensivo: NO sobreescribe la DB principal sin
# --target explicito.
#
# Con --recover rehace la casa tras un fallo total: la copia no lleva el .env, asi que
# se generan secretos nuevos y las API keys viejas dejan de valer (van con el pepper).
#
# Uso:
#   ./restore.sh DUMP_FILE                          # restaura a 'ecodb_restore_test', deja la DB
#   ./restore.sh DUMP_FILE --temp                   # restaura, smoke test, BORRA la DB
#   ./restore.sh DUMP_FILE --target=ecodb_v2        # restaura a DB con otro nombre
#   ./restore.sh DUMP_FILE --target=ecodb --allow-dangerous --recover [--env-file=.env] [--env=production]
#                [--key-targets=FICHERO]            # recuperacion completa
#
# --key-targets: una ruta por linea. En cada fichero se sustituye la clave ecodb_... por la
# nueva de la familia. Las rutas de cada casa viven fuera del repo. Las claves no se imprimen:
# quedan en .recovered_keys (permisos 600), junto al .env.
#
# Variables:
#   ECODB_CONTAINER  (default: ecodb-postgres)
#   ECODB_USER       (default: ecodb — debe tener CREATEDB)
#   ECODB_TARGET_DB  (default: ecodb_restore_test)

set -euo pipefail

# Todo nombre ${...} de docker-compose.yml esta en una de estas tres listas: lo comprueba
# api/tests/test_restore_env_guard.py.
# GENERATED_ENV: los rehace --recover. EXTERNAL_ENV: claves de terceros, las vuelve a poner el
# dueño. CONFIG_ENV: ajustes con valor por defecto, ningun secreto.
GENERATED_ENV="ECODB_DB_PASSWORD CELL_DB_PASSWORD ECODB_JWT_SECRET ECODB_API_KEY_PEPPER ECODB_API_KEY INTERNAL_BROADCAST_SECRET ENCRYPTION_KEY"
EXTERNAL_ENV="ANTHROPIC_API_KEY DEEPSEEK_API_KEY CELL_LLM_KEY TELEGRAM_BOT_TOKEN"
CONFIG_ENV="CELL_LLM_MODEL CELL_LLM_PROVIDER CELL_LLM_URL CONSOLIDATION_ALPHA CONSOLIDATION_BETA1 CONSOLIDATION_BETA2 CONSOLIDATION_BETA3 DEEPSEEK_URL ECODB_CORS_ORIGINS ECODB_ENV ECODB_LLM_PROVIDER FORESIGHT_CONFIDENCE_THRESHOLD FORESIGHT_SCAN_HOURS HF_CACHE_PATH LLM_THREADS MAX_MEMORIES_PER_WINDOW MIN_CLUSTER_SIZE RERANKER_ENABLED RERANKER_MODEL RERANKER_REVISION RERANK_FETCH_K SKILL_MIN_CASES SKILL_MIN_SUCCESS_RATE SKILL_STALE_THRESHOLD TELEGRAM_CHAT_ID THRESHOLD_NARRATIVE THRESHOLD_WORK WINDOWS_MEDIA_PREFIX"

# Git Bash en Windows convierte rutas estilo Unix /tmp/foo a C:/Users/.../Temp/foo
# antes de pasarlas a docker. Eso rompe pg_restore porque el path se aplica DENTRO
# del container Linux. Desactivamos la conversion para todos los docker exec/cp.
export MSYS_NO_PATHCONV=1

if [ "$#" -lt 1 ]; then
  echo "Uso: $0 DUMP_FILE [--target=DB] [--temp]" >&2
  exit 1
fi

DUMP_FILE="$1"
shift

CONTAINER="${ECODB_CONTAINER:-ecodb-postgres}"
PG_USER="${ECODB_USER:-ecodb}"
TARGET="${ECODB_TARGET_DB:-ecodb_restore_test}"
TEMP=false
RECOVER=false
ENV_FILE=".env"
KEY_TARGETS=""
RECOVER_ENV=""

for arg in "$@"; do
  case "$arg" in
    --target=*) TARGET="${arg#*=}" ;;
    --temp) TEMP=true ;;
    --recover) RECOVER=true ;;
    --env-file=*) ENV_FILE="${arg#*=}" ;;
    --key-targets=*) KEY_TARGETS="${arg#*=}" ;;
    --env=*)
      # #1083: una casa recuperada tras un fallo total arrancaba en desarrollo (el .env se perdió).
      # Con --env=production nace como la que se perdió; sin la opción, como una instalación nueva.
      RECOVER_ENV="${arg#*=}"
      case "$RECOVER_ENV" in development|production) ;;
        *) echo "[restore] ERROR — --env solo admite development o production (llegó: $RECOVER_ENV)" >&2; exit 1 ;;
      esac ;;
    --allow-dangerous) ;;  # RF3 fix — flag procesado mas abajo, aqui solo reconocido
    *) echo "[restore] arg desconocido: $arg" >&2; exit 1 ;;
  esac
done

if [ -n "$RECOVER_ENV" ] && ! $RECOVER; then
  echo "[restore] ERROR — --env solo tiene sentido con --recover" >&2
  exit 1
fi

if [ ! -f "$DUMP_FILE" ]; then
  echo "[restore] ERROR — dump file not found: $DUMP_FILE" >&2
  exit 1
fi

if $RECOVER && $TEMP; then
  echo "[restore] ERROR — --recover y --temp no van juntos: --temp borra la DB al acabar." >&2
  exit 1
fi

# RF2 fix (verificador) — blocklist de DBs protegidas. Sin este guard, --target=ecodb
# disparaba DROP DATABASE de la BD principal silenciosamente. Ahora rechazamos por
# defecto y exigimos --allow-dangerous explicito si alguien REALMENTE quiere
# sobreescribir la principal (ej. disaster recovery). Tres categorias:
#   - DBs del sistema postgres (jamas tocar): postgres, template0, template1
#   - DB principal de EcoDB (configurable): "$ECODB_DB" o ecodb por defecto
PROTECTED_DB="${ECODB_DB:-ecodb}"
SYSTEM_DBS=("postgres" "template0" "template1")
ALLOW_DANGEROUS=false
for arg in "$@"; do
  [ "$arg" = "--allow-dangerous" ] && ALLOW_DANGEROUS=true
done

# Iteracion para chequear contra todas las protegidas.
is_blocked=false
for db in "${SYSTEM_DBS[@]}"; do
  [ "$TARGET" = "$db" ] && is_blocked=true
done
[ "$TARGET" = "$PROTECTED_DB" ] && is_blocked=true

if $is_blocked && ! $ALLOW_DANGEROUS; then
  echo "[restore] ERROR — TARGET '$TARGET' es DB protegida (sistema o principal de EcoDB)." >&2
  echo "[restore] Si REALMENTE quieres sobreescribir, anade --allow-dangerous." >&2
  echo "[restore] Para verificar el dump sin riesgo: $0 \"$DUMP_FILE\" --temp" >&2
  exit 3
fi

DUMP_BASENAME=$(basename "$DUMP_FILE")
echo "[restore] $(date '+%Y-%m-%d %H:%M:%S') — $DUMP_FILE → DB '$TARGET' en '$CONTAINER'"

# UA1+OBS-2 fix (adv-code+verificador, convergente) — cleanup garantizado de la
# DB temporal si --temp y el script aborta a media restauracion. Sin este trap,
# pg_restore fallido dejaba ecodb_restore_test huerfana indefinidamente. EXIT
# trigger se dispara en exit normal o set -e abort.
if $TEMP; then
  trap 'docker exec "$CONTAINER" psql -U "$PG_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$TARGET\";" >/dev/null 2>&1 || true' EXIT
fi

# Convertir ruta del dump a estilo Windows si estamos en Git Bash.
if command -v cygpath >/dev/null 2>&1; then
  HOST_DUMP=$(cygpath -w "$DUMP_FILE")
else
  HOST_DUMP="$DUMP_FILE"
fi

# 1. Copiar dump al container.
docker cp "$HOST_DUMP" "$CONTAINER:/tmp/$DUMP_BASENAME"

# 2. Drop+create DB destino (postgres es DB neutral para conectar).
docker exec "$CONTAINER" psql -U "$PG_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$TARGET\";"
docker exec "$CONTAINER" psql -U "$PG_USER" -d postgres -c "CREATE DATABASE \"$TARGET\";"

# Compose crea ecodb_cell en un volumen nuevo; fuera de compose hay que crearlo. Sus permisos no van
# en la copia: los pone la api al arrancar.
docker exec "$CONTAINER" psql -q -U "$PG_USER" -d postgres -c "DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ecodb_cell') THEN CREATE ROLE ecodb_cell LOGIN; END IF;
END \$\$;"

# 3. Restaurar el dump, segun su formato.
if [ "$(head -c 5 "$DUMP_FILE" | tr -d '\0')" = "PGDMP" ]; then
  # pg_restore con formato custom — restaura DDL + data en orden correcto, sin owners ni ACLs.
  docker exec "$CONTAINER" pg_restore \
    --no-owner --no-acl \
    -U "$PG_USER" -d "$TARGET" \
    "/tmp/$DUMP_BASENAME"
else
  case "$DUMP_BASENAME" in
    *.gz) READ="gunzip -c" ;;
    *) READ="cat" ;;
  esac
  docker exec "$CONTAINER" sh -c \
    "$READ '/tmp/$DUMP_BASENAME' | psql -q -v ON_ERROR_STOP=1 -U '$PG_USER' -d '$TARGET' >/dev/null"
fi

# 4. Smoke test — verificar tablas + version del schema + counts basicos.
echo "[restore] smoke test:"
docker exec "$CONTAINER" psql -U "$PG_USER" -d "$TARGET" -c "
  SELECT version FROM schema_version;
  SELECT COUNT(*) AS users_count FROM users;
  SELECT COUNT(*) AS user_emails_count FROM user_emails;
  SELECT COUNT(*) AS agents_count FROM agents;
  SELECT COUNT(*) AS workspaces_count FROM workspaces;
  SELECT COUNT(*) AS projects_count FROM projects;
  SELECT COUNT(*) AS memories_count FROM memories;
  SELECT COUNT(*) AS triples_count FROM triples;
"

# 5. Limpiar dump dentro del container.
docker exec "$CONTAINER" rm "/tmp/$DUMP_BASENAME"

# Recuperacion completa. Los valores van por stdin o a ficheros: nada en la linea de comandos.
set_env() {
  local tmp
  tmp="$(mktemp)"
  if [ -f "$ENV_FILE" ]; then grep -v "^$1=" "$ENV_FILE" > "$tmp" || true; fi
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}
new_key() { printf 'ecodb_%s' "$(openssl rand 32 | openssl base64 -A | tr '+/' '-_' | tr -d '=')"; }
key_hash() { printf '%s%s' "$1" "$2" | sha256sum | cut -d' ' -f1; }

if $RECOVER; then
  DB_PASS=$(openssl rand -hex 16)
  CELL_PASS=$(openssl rand -hex 16)
  PEPPER=$(openssl rand -hex 32)
  FAMILY_KEY=$(new_key)
  MCP_KEY=$(new_key)
  STAMP=$(date '+%Y-%m-%d')

  # Lo que no se puede regenerar: se dice que era y luego se borra, porque su clave de cifrado
  # se perdio con el .env.
  echo "[restore] claves de proveedores que hay que volver a pegar:"
  docker exec "$CONTAINER" psql -At -U "$PG_USER" -d "$TARGET" \
    -c "SELECT '  - ' || provider || ' (' || coalesce(display_name, 'sin nombre') || ')' FROM llm_provider_keys ORDER BY id;"
  # #1083: la lista sale de EXTERNAL_ENV, para que no se quede atrás cuando se añada una.
  echo "  - $(echo "$EXTERNAL_ENV" | sed 's/ /, /g') en $ENV_FILE, si las usabas"

  docker exec -i "$CONTAINER" psql -q -U "$PG_USER" -d "$TARGET" <<SQL
\\set ON_ERROR_STOP on
BEGIN;
ALTER ROLE ecodb PASSWORD '$DB_PASS';
ALTER ROLE ecodb_cell PASSWORD '$CELL_PASS';
DELETE FROM llm_provider_keys;
UPDATE api_keys SET active = false WHERE active;
INSERT INTO api_keys (key_hash, name, user_id, active) VALUES
  ('$(key_hash "$PEPPER" "$FAMILY_KEY")', 'familia-$STAMP', 1, true),
  ('$(key_hash "$PEPPER" "$MCP_KEY")', 'mcp-service-$STAMP', 1, true);
COMMIT;
SQL

  set_env ECODB_DB_PASSWORD "$DB_PASS"
  set_env CELL_DB_PASSWORD "$CELL_PASS"
  set_env ECODB_JWT_SECRET "$(openssl rand -hex 32)"
  set_env ECODB_API_KEY_PEPPER "$PEPPER"
  set_env ECODB_API_KEY "$MCP_KEY"
  set_env INTERNAL_BROADCAST_SECRET "$(openssl rand -hex 32)"
  set_env ENCRYPTION_KEY "$(openssl rand -base64 32 | tr '+/' '-_')"
  if [ -n "$RECOVER_ENV" ]; then
    set_env ECODB_ENV "$RECOVER_ENV"
  else
    grep -q '^ECODB_ENV=' "$ENV_FILE" || set_env ECODB_ENV development
  fi
  grep -q '^ECODB_CORS_ORIGINS=' "$ENV_FILE" || set_env ECODB_CORS_ORIGINS http://localhost:8080,http://localhost:8091

  KEYS_FILE="$(dirname "$ENV_FILE")/.recovered_keys"
  ( umask 077; printf 'familia %s\nmcp-service %s\n' "$FAMILY_KEY" "$MCP_KEY" > "$KEYS_FILE" )
  if [ -n "$KEY_TARGETS" ]; then
    while IFS= read -r target || [ -n "$target" ]; do
      [ -z "$target" ] && continue
      if [ -f "$target" ]; then
        sed -i -E "s/ecodb_[A-Za-z0-9_-]{20,}/$FAMILY_KEY/g" "$target"
        echo "[restore] clave nueva en $target"
      else
        echo "[restore] AVISO — no existe $target: ponle a mano la clave de $KEYS_FILE" >&2
      fi
    done < "$KEY_TARGETS"
  fi
  echo "[restore] secretos nuevos en $ENV_FILE y claves en $KEYS_FILE."
  echo "[restore] Arranca el resto: docker compose up -d"
fi

# 6. Si --temp, borrar la DB tras smoke test (camino feliz). El trap EXIT cubre
# el caso de aborto antes de llegar aqui. UA2: IF EXISTS por defensividad —
# evita que la doble llamada (aqui + trap) emita ERROR si la DB ya no existe.
if $TEMP; then
  echo "[restore] --temp activo: borrando '$TARGET'"
  docker exec "$CONTAINER" psql -U "$PG_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$TARGET\";"
fi

echo "[restore] OK"
