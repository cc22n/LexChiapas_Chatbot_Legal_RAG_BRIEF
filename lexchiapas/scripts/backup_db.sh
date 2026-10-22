#!/usr/bin/env bash
# Backup de la base de datos de LexChiapas con pg_dump (formato custom, comprimido).
# Uso: DATABASE_URL=postgresql://user:pass@host:5432/db ./scripts/backup_db.sh [directorio]
# El directorio por defecto es ./backups. Conserva los ultimos 7 backups.
set -euo pipefail

: "${DATABASE_URL:?Falta DATABASE_URL}"

# pg_dump no entiende el prefijo de SQLAlchemy "postgresql+psycopg://".
PG_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"

DEST="${1:-./backups}"
mkdir -p "$DEST"

FILE="$DEST/lexchiapas_$(date +%Y%m%d_%H%M%S).dump"
pg_dump --format=custom --no-owner --no-privileges --file="$FILE" "$PG_URL"
echo "Backup creado: $FILE ($(du -h "$FILE" | cut -f1))"

# Rotacion: borra todo menos los 7 mas recientes.
ls -1t "$DEST"/lexchiapas_*.dump | tail -n +8 | xargs -r rm --
