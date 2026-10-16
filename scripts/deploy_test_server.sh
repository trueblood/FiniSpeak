#!/usr/bin/env bash
set -euo pipefail
umask 077

APP_ROOT=/var/www/finispeak
ENV_FILE=/etc/finispeak/finispeak.env
MIGRATION_CREDENTIAL=/etc/finispeak/firebase-service-account.json
MIGRATION_VENV=/opt/finispeak-migration-venv
FINALIZE_HELPER=/usr/local/libexec/finispeak/finalize_test_deployment.py
CUTOVER_ROOT=/var/lib/finispeak/cutover
STORAGE_MARKER="$CUTOVER_ROOT/firebase-storage-0003.complete"
DEPLOYMENT_MARKER="$CUTOVER_ROOT/firebase-free-deployment-0003.complete"
SERVICE_USER=finispeak
COMMIT_SHA="${1:-}"

fail() { echo "DEPLOYMENT FAILED: $1" >&2; exit 1; }
run_service() { runuser -u "$SERVICE_USER" -- "$@"; }
test "$(id -u)" = 0 || fail "run as root"
test "$(stat -c %U:%G "$0")" = root:root || fail "deployment helper ownership is unsafe"
test "$(stat -c %a "$0")" = 755 || fail "deployment helper mode is unsafe"
[[ "$COMMIT_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "a full commit SHA is required"
test -f "$ENV_FILE" || fail "production environment file is missing"
test -f "$FINALIZE_HELPER" || fail "root-owned environment finalizer is missing"
test "$(stat -c %U:%G "$FINALIZE_HELPER")" = root:root || fail "environment finalizer ownership is unsafe"
test "$(stat -c %a "$FINALIZE_HELPER")" = 755 || fail "environment finalizer mode is unsafe"
install -d -o root -g "$SERVICE_USER" -m 0750 "$CUTOVER_ROOT"
install -d -o root -g root -m 0700 /var/backups/finispeak

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

for key in MYSQL_HOST MYSQL_PORT MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD \
  OPENAI_API_KEY FINISPEAK_API_KEY_PEPPER FINISPEAK_JWT_SECRET \
  FINISPEAK_STORAGE_ROOT; do
  test -n "${!key:-}" || fail "required setting is missing: $key"
done
test "$MYSQL_DATABASE" = finispeak || fail "refusing non-finispeak deployment database"
test "$FINISPEAK_STORAGE_ROOT" = /var/lib/finispeak/private-files \
  || fail "refusing unexpected private-storage root"
test "${FINISPEAK_REPOSITORY_BACKEND:-mysql}" = mysql || fail "repository backend is not MySQL"
test "${FINISPEAK_MYSQL_PRIMARY_ENABLED:-}" = true || fail "MySQL primary is not enabled"
test "${FINISPEAK_COOKIE_SECURE:-}" = true || fail "secure cookies must remain enabled"

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$FINISPEAK_STORAGE_ROOT"
cd "$APP_ROOT"

# Alembic imports the application factory; migration mode deliberately avoids
# the production freshness gate while retaining the exact MySQL target.
export FINISPEAK_ENV=migration
current_revision="$(run_service ./venv/bin/alembic current 2>/dev/null | awk 'NF {print $1}' | tail -1)"
case "$current_revision" in
  20261013_0002)
    backup_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    backup_tmp="/var/backups/finispeak/.mysql-pre-0003-${backup_stamp}.sql.gz.tmp"
    backup_file="/var/backups/finispeak/mysql-pre-0003-${backup_stamp}.sql.gz"
    umask 077
    mysqldump --login-path=finispeak-backup --single-transaction --routines \
      --triggers --set-gtid-purged=OFF "$MYSQL_DATABASE" | gzip -9 > "$backup_tmp"
    gzip -t "$backup_tmp"
    mv "$backup_tmp" "$backup_file"
    sha256sum "$backup_file" > "${backup_file}.sha256"
    chmod 0600 "$backup_file" "${backup_file}.sha256"
    echo "MYSQL BACKUP VERIFIED file=$(basename "$backup_file")"
    run_service ./venv/bin/alembic upgrade 20261014_0003
    ;;
  20261014_0003) ;;
  *) fail "unexpected MySQL revision: ${current_revision:-none}" ;;
esac

if test "$current_revision" = 20261014_0003 && ! test -f "$DEPLOYMENT_MARKER"; then
  previous_backup="$(find /var/backups/finispeak -maxdepth 1 -type f -name 'mysql-pre-0003-*.sql.gz' -print | sort | tail -1)"
  test -n "$previous_backup" || fail "revision 0003 has no pre-migration backup"
  test -f "${previous_backup}.sha256" || fail "pre-migration backup checksum is missing"
  sha256sum --check --status "${previous_backup}.sha256" || fail "pre-migration backup checksum failed"
fi

test "$(run_service ./venv/bin/alembic current 2>/dev/null | awk 'NF {print $1}' | tail -1)" = 20261014_0003 \
  || fail "MySQL did not reach revision 0003"

activation_report="$CUTOVER_ROOT/account-activation-readiness-${COMMIT_SHA}.json"
run_service ./venv/bin/python scripts/check_account_activation_readiness.py > "$activation_report"
chmod 0600 "$activation_report"

initial_cutover=false
if test -f "$DEPLOYMENT_MARKER"; then
  test -f "$STORAGE_MARKER" || fail "completed cutover has no storage marker"
  echo "POST-CUTOVER MYSQL DEPLOYMENT legacy Firebase checks skipped"
else
  initial_cutover=true
  test -n "${FIREBASE_STORAGE_BUCKET:-}" || fail "initial cutover requires FIREBASE_STORAGE_BUCKET"
  test -f "$MIGRATION_CREDENTIAL" || fail "initial cutover requires the migration-only Firebase credential"
  if ! test -x "$MIGRATION_VENV/bin/python"; then
    install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$MIGRATION_VENV"
    run_service python3 -m venv "$MIGRATION_VENV"
  fi
  chown -R "$SERVICE_USER:$SERVICE_USER" "$MIGRATION_VENV"
  run_service "$MIGRATION_VENV/bin/python" -m pip install --disable-pip-version-check \
    -r "$APP_ROOT/requirements-migration.txt"
fi

run_storage_migration() {
  local report="$1"; shift
  runuser -u "$SERVICE_USER" -- env \
    MYSQL_HOST="$MYSQL_HOST" MYSQL_PORT="$MYSQL_PORT" MYSQL_DATABASE="$MYSQL_DATABASE" \
    MYSQL_USER="$MYSQL_USER" MYSQL_PASSWORD="$MYSQL_PASSWORD" \
    FINISPEAK_ENV=migration FINISPEAK_REPOSITORY_BACKEND=mysql \
    FINISPEAK_STORAGE_ROOT="$FINISPEAK_STORAGE_ROOT" \
    FIREBASE_STORAGE_BUCKET="$FIREBASE_STORAGE_BUCKET" \
    GOOGLE_APPLICATION_CREDENTIALS="$MIGRATION_CREDENTIAL" \
    "$MIGRATION_VENV/bin/python" "$APP_ROOT/scripts/migrate_firebase_storage.py" \
    --json-report "$@" > "$report"
  chown "$SERVICE_USER:$SERVICE_USER" "$report"
  chmod 0600 "$report"
}

storage_summary="$CUTOVER_ROOT/storage-summary-${COMMIT_SHA}.json"
if ! test -f "$STORAGE_MARKER"; then
  dry_report="$CUTOVER_ROOT/storage-dry-${COMMIT_SHA}.json"
  apply_report="$CUTOVER_ROOT/storage-apply-${COMMIT_SHA}.json"
  replay_report="$CUTOVER_ROOT/storage-replay-${COMMIT_SHA}.json"
  run_storage_migration "$dry_report"
  run_storage_migration "$apply_report" --apply
  run_storage_migration "$replay_report" --apply
  run_service ./venv/bin/python scripts/validate_storage_migration_reports.py \
    "$dry_report" "$apply_report" "$replay_report" > "$storage_summary"
  chmod 0600 "$storage_summary"
  cp "$storage_summary" "$STORAGE_MARKER"
  chmod 0600 "$STORAGE_MARKER"
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$FINISPEAK_STORAGE_ROOT"
find "$FINISPEAK_STORAGE_ROOT" -type d -exec chmod 0750 {} +
find "$FINISPEAK_STORAGE_ROOT" -type f -exec chmod 0640 {} +
run_service env FINISPEAK_STORAGE_OWNER="$SERVICE_USER" \
  ./venv/bin/python scripts/verify_private_storage.py \
  > "$CUTOVER_ROOT/storage-integrity-${COMMIT_SHA}.json"
chmod 0600 "$CUTOVER_ROOT/storage-integrity-${COMMIT_SHA}.json"

if test "$initial_cutover" = true; then
  # The legacy source is consulted once to prove the cutover. After the marker
  # is written, MySQL is authoritative and ordinary deployments stay Firebase-free.
  reconciliation="$CUTOVER_ROOT/reconciliation-${COMMIT_SHA}.log"
  GOOGLE_APPLICATION_CREDENTIALS="$MIGRATION_CREDENTIAL" \
  FIREBASE_CREDENTIALS="$MIGRATION_CREDENTIAL" \
  FINISPEAK_ENV=migration \
    run_service "$MIGRATION_VENV/bin/python" scripts/reconcile_firestore_mysql.py \
    --allow-target-additions > "$reconciliation" 2>&1
  chmod 0600 "$reconciliation"
  echo "INITIAL RECONCILIATION VERIFIED sha256=$(sha256sum "$reconciliation" | awk '{print $1}')"
fi

attestation="$CUTOVER_ROOT/deployment-attestation-${COMMIT_SHA}.txt"
{
  echo "commit=$COMMIT_SHA"
  echo "schema=20261014_0003"
  echo "database=finispeak"
  echo "storage_marker=$(test -f "$STORAGE_MARKER" && echo present)"
  if test "$initial_cutover" = true; then
    sha256sum "$reconciliation"
  else
    sha256sum "$DEPLOYMENT_MARKER"
  fi
  sha256sum "$CUTOVER_ROOT/storage-integrity-${COMMIT_SHA}.json"
  sha256sum "$activation_report"
  if test -f "$storage_summary"; then sha256sum "$storage_summary"; fi
} > "$attestation"
chmod 0600 "$attestation"

cp --preserve=mode,ownership,timestamps "$ENV_FILE" \
  "$CUTOVER_ROOT/finispeak.env.pre-${COMMIT_SHA}"
chmod 0600 "$CUTOVER_ROOT/finispeak.env.pre-${COMMIT_SHA}"

python3 "$FINALIZE_HELPER" \
  --environment-file "$ENV_FILE" --attestation-file "$attestation" --commit "$COMMIT_SHA" \
  > "$CUTOVER_ROOT/environment-update-${COMMIT_SHA}.json"
chmod 0600 "$CUTOVER_ROOT/environment-update-${COMMIT_SHA}.json"

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
export FINISPEAK_ENV=production
run_service ./venv/bin/python scripts/production_readiness_check.py --production
run_service ./venv/bin/python -c 'from repositories.config import cutover_safety; cutover_safety()'
run_service ./venv/bin/alembic current 2>/dev/null | grep -q 20261014_0003

systemctl restart finispeak.service
systemctl is-active --quiet finispeak.service
ready_url="${FINISPEAK_INTERNAL_READY_URL:-http://127.0.0.1:8080/api/ready}"
curl --fail --silent --show-error --retry 15 --retry-delay 2 --retry-connrefused "$ready_url" |
  ./venv/bin/python -c 'import json,sys; p=json.load(sys.stdin); b=p.get("repositoryBackends",{}); expected={"accounts","translators","calls","participants","transcripts","reviews","organizations","api_access","taxonomy","language_metrics"}; assert p.get("status")=="ready"; assert p.get("deploymentProfile")=="test"; assert p.get("schemaRevision")=="20261014_0003"; assert set(b)==expected and set(b.values())=={"mysql"}'

main_pid="$(systemctl show --property MainPID --value finispeak.service)"
test "$main_pid" -gt 1 || fail "service has no main process"
if tr '\0' '\n' < "/proc/$main_pid/environ" | grep -Eq '^(FIREBASE_CREDENTIALS|GOOGLE_APPLICATION_CREDENTIALS)='; then
  fail "Firebase credentials leaked into the runtime process"
fi
run_service env FINISPEAK_TEST_DEPLOYMENT=true \
  ./venv/bin/python scripts/verify_deployed_test_server.py \
  --base-url http://127.0.0.1:8080
run_service env FINISPEAK_STORAGE_OWNER="$SERVICE_USER" \
  ./venv/bin/python scripts/verify_private_storage.py \
  > "$CUTOVER_ROOT/storage-integrity-post-smoke-${COMMIT_SHA}.json"
chmod 0600 "$CUTOVER_ROOT/storage-integrity-post-smoke-${COMMIT_SHA}.json"

printf 'commit=%s\nschema=20261014_0003\nstatus=verified\n' "$COMMIT_SHA" > "$DEPLOYMENT_MARKER"
chmod 0600 "$DEPLOYMENT_MARKER"
printf 'STORAGE MIGRATION VERIFIED '
cat "$STORAGE_MARKER"
printf 'PRIVATE STORAGE VERIFIED '
cat "$CUTOVER_ROOT/storage-integrity-post-smoke-${COMMIT_SHA}.json"
printf 'ACCOUNT ACTIVATION READY '
cat "$activation_report"
echo "DEPLOYMENT VERIFIED commit=$COMMIT_SHA schema=20261014_0003"
