#!/usr/bin/env bash
# Restaura un backup generado por backup_db.sh en una base de datos VACIA.
# Uso: DATABASE_URL=postgresql://user:pass@host:5432/db_nueva ./scripts/restore_db.sh archivo.dump
# Requiere la extension pgvector instalada en el servidor destino.
# Para probar el backup, restaura en una base temporal, no en la de produccion.
set -euo pipefail

: "${DATABASE_URL:?Falta DATABASE_URL}"
FILE="${1:?Uso: restore_db.sh archivo.dump}"

PG_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"

psql "$PG_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
pg_restore --no-owner --no-privileges --dbname="$PG_URL" "$FILE"
echo "Restauracion completada desde $FILE"
