#!/usr/bin/env bash
# Restore a backup made by backup.sh into a NEW database, then verify it. Never restores over an existing database.
# See docs/OPERATIONS.md §Backup & restore.
#
#   infra/backup/restore.sh <backup-dir> <target-database>
#
# Environment: as backup.sh, plus PG_RESTORE (default: pg_restore; dev: "docker compose exec -T postgres pg_restore
# -U abos"). The role `abos_app` must exist on the target server (migration 0001 creates it; on managed Postgres
# create it up front: CREATE ROLE abos_app NOLOGIN NOINHERIT; GRANT abos_app TO <login>).
set -euo pipefail

dir="${1:?usage: restore.sh <backup-dir> <target-database>}"
target="${2:?usage: restore.sh <backup-dir> <target-database>}"
PSQL="${PSQL:-psql}"
PG_RESTORE="${PG_RESTORE:-pg_restore}"
admin_db="${PGDATABASE:-postgres}"

( cd "$dir" && sha256sum -c --quiet SHA256SUMS ) || { echo "checksum mismatch in $dir" >&2; exit 1; }

exists="$($PSQL -d "$admin_db" -At -c "SELECT 1 FROM pg_database WHERE datname = '$target'")"
[ -z "$exists" ] || { echo "database $target already exists; restore only into a new database" >&2; exit 1; }
$PSQL -d "$admin_db" -q -c "CREATE DATABASE \"$target\""

# --exit-on-error + one transaction: a partial restore is worse than none. The dump creates the pgvector extension
# (IF NOT EXISTS); on managed Postgres enable it on the new database first if the restoring login can't.
$PG_RESTORE -d "$target" --exit-on-error --single-transaction < "$dir/database.dump"

# Verify: same migration revision and the same row count in every table.
rev="$($PSQL -d "$target" -At -c "SELECT version_num FROM alembic_version")"
[ "$rev" = "$(cat "$dir/alembic_revision")" ] || { echo "revision mismatch: $rev" >&2; exit 1; }
$PSQL -d "$target" -At -F $'\t' -c "
  SELECT c.relname, (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I', c.relname), false, true, '')))[1]::text
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1" > "$dir/.restored_counts.tsv"
diff -u "$dir/row_counts.tsv" "$dir/.restored_counts.tsv" || { echo "row counts differ" >&2; exit 1; }
rls="$($PSQL -d "$target" -At -c "SELECT count(*) FROM pg_policies WHERE policyname = 'tenant_isolation'")"
triggers="$($PSQL -d "$target" -At -c "SELECT count(*) FROM pg_trigger WHERE tgname LIKE '%_append_only' OR tgname LIKE '%_write_once'")"
echo "restored $target: revision $rev, $(wc -l < "$dir/row_counts.tsv") tables, $rls RLS policies, $triggers ledger triggers"
if [ -f "$dir/storage.tar.gz" ]; then
  echo "storage archive present: extract with  tar -C <ABOS_STORAGE_DIR> -xzf $dir/storage.tar.gz"
fi
