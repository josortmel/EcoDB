# EcoDB scripts

## Backups

```bash
# Backup manual (default: container ecodb-postgres-test, DB ecodb)
bash scripts/backup.sh

# Override via env vars
ECODB_CONTAINER=ecodb-postgres-prod \
ECODB_BACKUP_DIR=/var/backups/ecodb \
ECODB_KEEP=60 \
  bash scripts/backup.sh
```

Salida: `<repo>/backups/ecodb_<YYYYMMDD>_<HHMMSS>.dump` (formato `pg_dump --format=custom --compress=6`).

Retencion: mantiene los ultimos `ECODB_KEEP=30` dumps por defecto.

## Restore

```bash
# Restaurar a DB temporal 'ecodb_restore_test' (smoke test, deja la DB)
bash scripts/restore.sh backups/ecodb_20260507_233611.dump

# Restaurar, smoke test y borrar la DB temporal (cron de verificacion)
bash scripts/restore.sh backups/ecodb_20260507_233611.dump --temp

# Restaurar a otro nombre de DB
bash scripts/restore.sh backups/foo.dump --target=ecodb_v2
```

Smoke test que ejecuta tras restaurar:
- `SELECT version FROM schema_version` (debe coincidir con la del backup).
- `COUNT(*)` en users, user_emails, agents, workspaces, projects, memories, triples.

`--temp` es seguro como verificacion automatica desde cron — restaura, valida, borra.
Si el restore falla a media transaccion, el trap EXIT garantiza que la DB temporal
se borra igualmente (no quedan huerfanas).

### Sobreescribir la DB principal (peligroso, solo para disaster recovery)

Por defecto, el script REHUSA si `--target` apunta a una DB protegida (la principal
de EcoDB o cualquier DB de sistema postgres/template0/template1). Si REALMENTE
necesitas sobreescribir la BD principal — disaster recovery, restore desde backup
remoto tras corrupcion — usa `--allow-dangerous`:

```bash
# DESTRUYE la BD ecodb principal y la reemplaza con el dump.
bash scripts/restore.sh backups/ecodb_YYYYMMDD.dump --target=ecodb --allow-dangerous
```

Antes de ejecutar esto, **verifica el dump primero** con `--temp` en una DB temporal
y revisa el smoke test. Si tienes dudas, no lo hagas — pregunta primero.

## Cron del host

### Linux (VPS)

`cron` por defecto NO hereda `$PATH` del usuario. `docker` suele estar en
`/usr/local/bin/docker` o `/usr/bin/docker` segun la instalacion. Sin PATH
explicito, el script falla silencioso con `command not found: docker` en el log.
**Siempre incluye PATH al inicio del crontab.**

```cron
PATH=/usr/local/bin:/usr/bin:/bin

# Backup diario a las 03:17 (off-peak, evita el "0 *" estampida)
17 3 * * * cd /opt/ecodb && bash scripts/backup.sh >> /var/log/ecodb-backup.log 2>&1

# Verificacion semanal: ultimo backup debe restaurar limpio
23 4 * * 0 cd /opt/ecodb && bash scripts/restore.sh "$(ls -1t backups/*.dump | head -1)" --temp >> /var/log/ecodb-restore-check.log 2>&1
```

### Windows (Task Scheduler)

**Pre-condicion obligatoria** — crear el directorio `backups/` antes de activar
la tarea. El comando del Action redirige el output con `>>` y bash abre el archivo
de log ANTES de ejecutar `backup.sh` (que es quien hace `mkdir -p` del directorio).
Si el directorio no existe en el primer run, bash falla al abrir el log y la tarea
nunca se ejecuta. Workaround: crear `backups/` manualmente UNA vez al instalar.

```bash
# Una sola vez tras clonar el proyecto en Windows
mkdir backups
```

1. Abrir Task Scheduler → Create Basic Task.
2. Trigger: Daily at 03:17.
3. Action: Start a program.
4. Program: `C:\Program Files\Git\bin\bash.exe`
5. Arguments: `-c "cd /c/path/to/ecodb && bash scripts/backup.sh >> /c/path/to/ecodb/backups/backup.log 2>&1"`
6. Settings → Run whether user is logged in or not.

Tarea separada para verificacion semanal con `restore.sh ... --temp`.

## Pre-condiciones

- Docker Desktop / Docker Engine corriendo.
- Container `$ECODB_CONTAINER` activo.
- Usuario `$ECODB_USER` con permisos: `pg_dump` necesita READ en todas las tablas; `restore.sh` requiere `CREATEDB` para el DROP/CREATE de la DB temporal.
- En Git Bash: el script detecta `cygpath` y convierte rutas de host a estilo Windows automaticamente.

## Off-site (deuda)

Hoy backups locales solamente. Off-site options:
- rsync a VPS secundario, o
- aws s3 sync con cifrado servidor (KMS), o
- Backblaze B2 + rclone.
