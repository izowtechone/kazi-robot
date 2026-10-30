#!/usr/bin/env bash
# Usage: ./scripts/restore.sh backups/kazirobot_YYYYmmdd_HHMMSS.sql.gz
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f "${1:-}" ] || { echo "Usage: $0 <backup.sql.gz>"; exit 1; }
set -a; . ./.env; set +a
read -r -p "This overwrites the current database. Continue? [y/N] " ok
[ "$ok" = "y" ] || exit 1
docker compose stop worker beat backend
gunzip -c "$1" | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
docker compose start backend worker beat
echo "Restore complete."
