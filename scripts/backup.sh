#!/usr/bin/env bash
# Usage: ./scripts/backup.sh   (cron: 0 2 * * * cd /opt/kazi-robot && ./scripts/backup.sh)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
mkdir -p backups
FILE="backups/kazirobot_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists | gzip > "$FILE"
find backups -name '*.sql.gz' -mtime +${KEEP_DAYS:-14} -delete
echo "Backup written: $FILE"
