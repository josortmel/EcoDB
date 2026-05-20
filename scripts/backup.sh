#!/usr/bin/env bash
# EcoDB backup — Tarea 1.13 plan maestro v3 §6.3 + §8 Fase 1.
# Ejecuta pg_dump dentro del container postgres y copia el dump al host.
#
# Uso:
#   ./backup.sh                              # defaults (ecodb-postgres-test)
#   ECODB_CONTAINER=foo ./backup.sh         # override via env vars
#
# Variables:
#   ECODB_CONTAINER  (default: ecodb-postgres-test)
#   ECODB_DB         (default: ecodb)
#   ECODB_USER       (default: ecodb)
#   ECODB_BACKUP_DIR (default: <repo>/backups)
#   ECODB_KEEP       (default: 30 — backups a mantener)
#
# Salida: <out_dir>/ecodb_<YYYYMMDD>_<HHMMSS>.dump (formato custom de pg_dump).

set -euo pipefail

# Git Bash en Windows convierte rutas estilo Unix /tmp/foo a C:/Users/.../Temp/foo
# antes de pasarlas a docker. Eso rompe pg_dump porque el path se aplica DENTRO
# del container Linux. Desactivamos la conversion para todos los docker exec.
export MSYS_NO_PATHCONV=1

CONTAINER="${ECODB_CONTAINER:-ecodb-postgres-test}"
DB="${ECODB_DB:-ecodb}"
PG_USER="${ECODB_USER:-ecodb}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${ECODB_BACKUP_DIR:-$SCRIPT_DIR/../backups}"
KEEP="${ECODB_KEEP:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="ecodb_${TIMESTAMP}.dump"

# RF1 fix (verificador) — validar KEEP. Antes, KEEP=0 borraba TODOS los dumps
# incluido el recien creado, dejando 0 backups con exit 0 silencioso.
# Convencion clara: KEEP=0 significa "sin retencion, no borrar nada".
if ! [[ "$KEEP" =~ ^[0-9]+$ ]]; then
  echo "[backup] ERROR — ECODB_KEEP debe ser un entero >= 0, got: $KEEP" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"

echo "[backup] $(date '+%Y-%m-%d %H:%M:%S') — container=$CONTAINER db=$DB user=$PG_USER"
echo "[backup] target: $OUT_DIR/$DUMP_FILE"

# Para docker cp y docker run --volume necesitamos rutas estilo Windows
# en Git Bash (cygpath -w). En Linux/macOS cygpath no existe → ruta tal cual.
if command -v cygpath >/dev/null 2>&1; then
  HOST_OUT=$(cygpath -w "$OUT_DIR")
else
  HOST_OUT="$OUT_DIR"
fi

# 1. pg_dump dentro del container (formato custom — comprimido + reorganizable).
# BC3 (adv-code): --no-owner/--no-acl son no-ops en formato custom (solo aplican
# a formato plain). El dump siempre incluye owners/ACLs. Las flags se aplican en
# pg_restore donde si tienen efecto.
docker exec "$CONTAINER" pg_dump \
  -U "$PG_USER" -d "$DB" \
  --format=custom --compress=6 \
  -f "/tmp/$DUMP_FILE"

# 2. Copiar al host (HOST_OUT con backslashes en Windows, slash directo en Unix).
docker cp "$CONTAINER:/tmp/$DUMP_FILE" "$HOST_OUT/$DUMP_FILE"

# 3. Limpiar dump dentro del container.
docker exec "$CONTAINER" rm "/tmp/$DUMP_FILE"

# 4. Verificacion de integridad — pg_restore --list lee el header.
IMAGE=$(docker inspect "$CONTAINER" --format '{{.Config.Image}}')
if ! docker run --rm -v "$HOST_OUT:/dump:ro" --entrypoint pg_restore "$IMAGE" \
        --list "/dump/$DUMP_FILE" > /dev/null 2>&1; then
  echo "[backup] WARN — pg_restore --list fallo en verificacion de integridad" >&2
fi

# Tamano del dump.
if SIZE=$(stat -c%s "$OUT_DIR/$DUMP_FILE" 2>/dev/null); then
  :
elif SIZE=$(stat -f%z "$OUT_DIR/$DUMP_FILE" 2>/dev/null); then
  :
else
  SIZE="?"
fi
echo "[backup] OK — $OUT_DIR/$DUMP_FILE ($SIZE bytes)"

# 5. Retencion: mantener solo los ultimos N backups. RF1: KEEP=0 = sin retencion.
if [ "$KEEP" -eq 0 ]; then
  echo "[backup] retencion deshabilitada (ECODB_KEEP=0)"
else
  # BC1 (adv-code): set -e + ls glob no-match → wc imprime 0 pero pipe exit 2.
  # Anadimos `|| echo 0` al final para que la asignacion no aborte cuando no hay
  # dumps todavia (primer run o tras un retencion=0 borrado manual).
  COUNT=$(ls -1 "$OUT_DIR"/ecodb_*.dump 2>/dev/null | wc -l | tr -d ' ' || echo 0)
  if [ "$COUNT" -gt "$KEEP" ]; then
    TO_DELETE=$((COUNT - KEEP))
    echo "[backup] retencion: borrando $TO_DELETE backups antiguos (mantener $KEEP)"
    ls -1t "$OUT_DIR"/ecodb_*.dump | tail -n "$TO_DELETE" | while read -r old; do
      rm -v "$old"
    done
  fi
fi

echo "[backup] DONE"
