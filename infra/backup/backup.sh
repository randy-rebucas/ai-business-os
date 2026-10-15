#!/usr/bin/env bash
# Back up AI Business OS: Postgres (custom-format dump, includes RLS policies, triggers and grants) + object storage.
# See docs/OPERATIONS.md §Backup & restore.
#
#   infra/backup/backup.sh <output-dir>
#
# Environment:
#   PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE   connection as the table OWNER (not abos_app — RLS would hide rows)
#   PG_DUMP     pg_dump command (default: pg_dump). Dev: PG_DUMP="docker compose exec -T postgres pg_dump -U abos"
#   PSQL        psql command (default: psql).      Dev: PSQL="docker compose exec -T postgres psql -U abos"
#   STORAGE_DIR local storage dir to archive (ABOS_STORAGE_BACKEND=local). With S3, rely on bucket versioning /
#               replication instead and leave this unset.
set -euo pipefail

out="${1:?usage: backup.sh <output-dir>}"
db="${PGDATABASE:-abos}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dir="$out/abos-$stamp"
mkdir -p "$dir"
PG_DUMP="${PG_DUMP:-pg_dump}"
PSQL="${PSQL:-psql}"

# Migration revision and per-table row counts: the restore check compares against these.
$PSQL -d "$db" -At -c "SELECT version_num FROM alembic_version" > "$dir/alembic_revision"
$PSQL -d "$db" -At -F $'\t' -c "
  SELECT c.relname, (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I', c.relname), false, true, '')))[1]::text
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1" > "$dir/row_counts.tsv"

# Custom format: compressed, restorable selectively, consistent snapshot of the whole database.
$PG_DUMP -d "$db" -Fc > "$dir/database.dump"

if [ -n "${STORAGE_DIR:-}" ]; then
  tar -C "$STORAGE_DIR" -czf - . > "$dir/storage.tar.gz"  # via stdout: GNU tar reads "C:/..." as host:path
fi

( cd "$dir" && sha256sum ./* > SHA256SUMS )
echo "$dir"
