#!/usr/bin/env bash
# EcoDB restore — Tarea 1.13 plan maestro v3 §6.3 + §8 Fase 1.
# Restaura un dump de pg_dump (formato custom) a una DB temporal y verifica
# integridad. Uso defensivo: NO sobreescribe la DB principal sin --target explicito.
#
# Uso:
#   ./restore.sh DUMP_FILE                          # restaura a 'ecodb_restore_test', deja la DB
#   ./restore.sh DUMP_FILE --temp                   # restaura, smoke test, BORRA la DB
#   ./restore.sh DUMP_FILE --target=ecodb_v2        # restaura a DB con otro nombre
#
# Variables:
#   ECODB_CONTAINER  (default: ecodb-postgres)
#   ECODB_USER       (default: ecodb — debe tener CREATEDB)
#   ECODB_TARGET_DB  (default: ecodb_restore_test)

set -euo pipefail

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

for arg in "$@"; do
  case "$arg" in
    --target=*) TARGET="${arg#*=}" ;;
    --temp) TEMP=true ;;
    --allow-dangerous) ;;  # RF3 fix — flag procesado mas abajo, aqui solo reconocido
    *) echo "[restore] arg desconocido: $arg" >&2; exit 1 ;;
  esac
done

if [ ! -f "$DUMP_FILE" ]; then
  echo "[restore] ERROR — dump file not found: $DUMP_FILE" >&2
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

# 3. Restaurar el dump.
# pg_restore con formato custom — restaura DDL + data en orden correcto, sin owners ni ACLs.
docker exec "$CONTAINER" pg_restore \
  --no-owner --no-acl \
  -U "$PG_USER" -d "$TARGET" \
  "/tmp/$DUMP_BASENAME"

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

# 6. Si --temp, borrar la DB tras smoke test (camino feliz). El trap EXIT cubre
# el caso de aborto antes de llegar aqui. UA2: IF EXISTS por defensividad —
# evita que la doble llamada (aqui + trap) emita ERROR si la DB ya no existe.
if $TEMP; then
  echo "[restore] --temp activo: borrando '$TARGET'"
  docker exec "$CONTAINER" psql -U "$PG_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$TARGET\";"
fi

echo "[restore] OK"
