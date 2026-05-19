#!/bin/bash
set -euo pipefail

# PostgreSQL database backup script.
#
# Required tool: pg_dump
# Optional tool: sha256sum (Linux) or shasum (macOS fallback)
#
# Environment variables:
#   PGHOST                 default: localhost
#   PGPORT                 default: 5432
#   PGUSER                 default: postgres
#   PGDATABASE             default: duoduo
#   PGPASSWORD             provided by caller; never hardcoded here
#   BACKUP_DIR             default: /backups
#   BACKUP_RETENTION_DAYS  default: 7

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-duoduo}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

timestamp="$(date +'%Y%m%d_%H%M%S')"
backup_name="duoduo_backup_${timestamp}.sql.gz"
backup_path="${BACKUP_DIR}/${backup_name}"
tmp_path="${backup_path}.tmp"

log() {
  printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

sha256_file() {
  local file_path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file_path" | awk '{print $1}'
    return
  fi
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file_path" | awk '{print $1}'
    return
  fi
  log "ERROR: sha256sum or shasum is required to print checksum"
  return 1
}

cleanup_tmp() {
  rm -f "$tmp_path"
}

trap cleanup_tmp EXIT

mkdir -p "$BACKUP_DIR"

log "Starting PostgreSQL backup"
log "Database: ${PGDATABASE}"
log "Host: ${PGHOST}:${PGPORT}"
log "User: ${PGUSER}"
log "Backup file: ${backup_path}"

pg_dump \
  --host="$PGHOST" \
  --port="$PGPORT" \
  --username="$PGUSER" \
  --dbname="$PGDATABASE" \
  --format=plain \
  --no-owner \
  --no-privileges \
  | gzip -c > "$tmp_path"

mv "$tmp_path" "$backup_path"

size_bytes="$(wc -c < "$backup_path" | tr -d '[:space:]')"
checksum="$(sha256_file "$backup_path")"

log "Backup completed"
log "File: ${backup_path}"
log "Size: ${size_bytes} bytes"
log "SHA256: ${checksum}"

log "Removing backups older than ${BACKUP_RETENTION_DAYS} day(s)"
find "$BACKUP_DIR" \
  -type f \
  -name 'duoduo_backup_*.sql.gz' \
  -mtime +"$BACKUP_RETENTION_DAYS" \
  -print \
  -delete

log "Backup retention cleanup completed"
