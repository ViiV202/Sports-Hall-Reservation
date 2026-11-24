#!/usr/bin/env bash
# اسکریپت بکاپ روزانه PostgreSQL روی سرور لینوکس (قابل اجرا در crontab)
# نمونه کران‌جاب روزانه ساعت ۳ بامداد:
# 0 3 * * * /path/to/project/backup_db.sh >> /var/log/team_finder_backup.log 2>&1

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
CONTAINER_NAME="${CONTAINER_NAME:-team_finder_db}"
POSTGRES_USER="${POSTGRES_USER:-team_admin}"
POSTGRES_DB="${POSTGRES_DB:-team_finder}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

mkdir -p "$BACKUP_DIR"
TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"
OUT_FILE="${BACKUP_DIR}/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

echo "[$(date)] Starting PostgreSQL backup -> ${OUT_FILE}"
docker exec "$CONTAINER_NAME" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$OUT_FILE"

find "$BACKUP_DIR" -name "${POSTGRES_DB}_*.sql.gz" -type f -mtime +"$RETENTION_DAYS" -delete
echo "[$(date)] Backup completed successfully."
