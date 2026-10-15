# Phase 4–5 MySQL read/write cutover (historical)

> Superseded for current operations by `docs/FIREBASE_REMOVAL.md`. This records
> the staged cutover and must not be used to reactivate Firestore or shadow
> routing.

## Safety model

Firestore remains the default. `firestore` routes durable reads and writes to
Firestore. `shadow` returns Firestore results and compares read-only MySQL
results; it never writes MySQL. `mysql` routes durable reads and writes only to
MySQL. Shadow writes are deliberately rejected because two independently
committed primaries can split brain.

Firebase Authentication, Storage, and the `calls/{call}/connections` WebRTC
offer/answer and ICE-candidate documents remain Firebase dependencies. They are
not durable application records. The browser no longer reads or writes durable
users, emailDirectory, profiles, calls, participants, transcripts, reviews, or
taxonomy documents directly.

## Pre-cutover checks (mandatory)

1. Take and verify a DigitalOcean backup using
   `DIGITALOCEAN_MYSQL_BACKUP_RESTORE.md`. Record the backup identifier outside
   application logs.
2. Confirm `alembic current` reports `20261014_0003`. Do not run Alembic from
   the web process.
3. Stop all Phase 3 catch-up workers only after their checkpoints are idle and
   no batch is retrying. Confirm the transactional outbox has no failed rows.
4. Run a fresh production-target dry run, catch-up, and reconciliation. The
   earlier 229-record isolated-database result is not evidence that production
   is current.

   ```bash
   python -m scripts.sync_firestore_to_mysql
   FINISPEAK_FIRESTORE_MYSQL_SYNC_ENABLED=true \
     python -m scripts.sync_firestore_to_mysql --apply --retries 3
   python -m scripts.reconcile_firestore_mysql 2>&1 | tee /secure/operator/finispeak-reconcile.log
   sha256sum /secure/operator/finispeak-reconcile.log
   ```

   Run the apply and reconciliation again after the first pass. If deletions
   are expected, review two complete successful scans before using the
   separately gated `--apply-deletions` procedure in the Phase 3 runbook.
5. Require zero missing IDs, zero unexpected IDs, zero canonical hash
   mismatches, zero unresolved tombstones, and zero relationship errors for
   every collection. Store the report securely; it can contain identifiers.
6. Compute the SHA-256 digest of the final redacted reconciliation report. Set
   `FINISPEAK_MYSQL_RECONCILED_AT` to its UTC completion time and
   `FINISPEAK_MYSQL_RECONCILIATION_DIGEST` to that digest. The attestation
   expires after 30 minutes by default.
7. Exercise account bootstrap/profile, interpreter private profile, discovery,
   call creation/state, participants, transcription, review, organization,
   commercial API quota, taxonomy, and metrics against a staging MySQL 8 clone.

## Exact production catch-up and attestation commands

Run these commands as an operator on the DigitalOcean host only after the
verified backup is complete and durable-write traffic has been drained. The
database assertion is intentional: do not weaken or remove it. These commands
do not apply deletions. A deletion catch-up remains the separately gated Phase
3 procedure.

```bash
sudo -s
cd /var/www/finispeak
set -euo pipefail
set -a
. /etc/finispeak/finispeak.env
set +a

test "${MYSQL_DATABASE:?MYSQL_DATABASE is required}" = "finispeak" || {
  echo "Refusing non-production or unexpected database: ${MYSQL_DATABASE:-unset}" >&2
  exit 90
}
test "${FINISPEAK_REPOSITORY_BACKEND:-firestore}" = "firestore" || {
  echo "Catch-up must run while Firestore is primary" >&2
  exit 91
}
for DOMAIN in ACCOUNTS TRANSLATORS CALLS PARTICIPANTS TRANSCRIPTS REVIEWS \
  ORGANIZATIONS API_ACCESS TAXONOMY LANGUAGE_METRICS; do
  FLAG="FINISPEAK_REPOSITORY_${DOMAIN}"
  test "${!FLAG:-firestore}" = "firestore" || {
    echo "Catch-up refused: ${FLAG} is not firestore" >&2
    exit 92
  }
done

/var/www/finispeak/venv/bin/alembic current
mysql --batch --skip-column-names "$MYSQL_DATABASE" -e \
  "SELECT version_num FROM alembic_version;"

# Read-only enumeration first.
FINISPEAK_FIRESTORE_MYSQL_SYNC_ENABLED=false \
  /var/www/finispeak/venv/bin/python -m scripts.sync_firestore_to_mysql

# Upserts only. Run twice; the second summary must report every record as a
# duplicate and zero upserts, stale events, conflicts, errors, or deletions.
FINISPEAK_FIRESTORE_MYSQL_SYNC_ENABLED=true \
FINISPEAK_FIRESTORE_MYSQL_DELETE_ENABLED=false \
  /var/www/finispeak/venv/bin/python -m scripts.sync_firestore_to_mysql --apply --retries 3
FINISPEAK_FIRESTORE_MYSQL_SYNC_ENABLED=true \
FINISPEAK_FIRESTORE_MYSQL_DELETE_ENABLED=false \
  /var/www/finispeak/venv/bin/python -m scripts.sync_firestore_to_mysql --apply --retries 3

# Fail if synchronization or outbox telemetry is unhealthy.
test "$(mysql --batch --skip-column-names "$MYSQL_DATABASE" -e \
  "SELECT COUNT(*) FROM sync_checkpoints WHERE status <> 'idle' OR error_count <> 0;")" = "0"
test "$(mysql --batch --skip-column-names "$MYSQL_DATABASE" -e \
  "SELECT COUNT(*) FROM transactional_outbox WHERE status = 'failed';")" = "0"

# The log is mode 0600 and contains counts plus hashed identifiers, never
# document contents. A nonzero reconciliation exit aborts this command block.
install -d -m 0700 /var/lib/finispeak/cutover
umask 077
ATTESTATION_FILE="/var/lib/finispeak/cutover/reconcile-$(date -u +%Y%m%dT%H%M%SZ).log"
/var/www/finispeak/venv/bin/python -m scripts.reconcile_firestore_mysql \
  2>&1 | tee "$ATTESTATION_FILE"
ATTESTATION_SHA256="$(sha256sum "$ATTESTATION_FILE" | awk '{print $1}')"
ATTESTATION_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'FINISPEAK_MYSQL_RECONCILED_AT=%s\n' "$ATTESTATION_UTC"
printf 'FINISPEAK_MYSQL_RECONCILIATION_DIGEST=%s\n' "$ATTESTATION_SHA256"
```

The reconciliation output must show identical source and target counts and
zero missing, extra, and mismatched records for every collection. Copy the two
printed attestation values into `/etc/finispeak/finispeak.env` together with
the activation values below. An attestation from
`finispeak_migration_test`, staging, or an earlier run is deliberately invalid
for production activation.

## Shadow comparison

Set all MySQL connection variables, set
`FINISPEAK_SHADOW_COMPARISON_ENABLED=true`, and select `shadow` globally or by
domain. Leave `FINISPEAK_SHADOW_WRITES_ENABLED=false`. `/api/ready` reports
comparison, mismatch, and error counters without exposing record content.
Investigate all mismatches; never use the shadow copy as a fallback response.

## MySQL-primary activation

Use one maintenance change with these values only after the preflight passes:

```text
FINISPEAK_REPOSITORY_BACKEND=mysql
FINISPEAK_MYSQL_PRIMARY_ENABLED=true
FINISPEAK_MYSQL_EXPECTED_REVISION=20261014_0003
FINISPEAK_MYSQL_RECONCILED_AT=<fresh UTC timestamp>
FINISPEAK_MYSQL_RECONCILIATION_DIGEST=<64 lowercase hex characters>
FINISPEAK_SHADOW_COMPARISON_ENABLED=false
FINISPEAK_SHADOW_WRITES_ENABLED=false
```

Remove any `FINISPEAK_REPOSITORY_<DOMAIN>` overrides, or explicitly set every
listed domain to `mysql`; a leftover per-domain Firestore override is not a
valid full cutover.

Dependency checks reject unsafe partial routing (for example calls on MySQL
while accounts remain on Firestore). Start one instance, require `/api/ready`
to pass, execute the staging smoke-test sequence against it, then roll the
remaining instances. Do not send durable writes to Firestore after the first
MySQL-primary instance accepts traffic.

Monitor HTTP error rate, DB connection saturation, deadlocks, stale-write
conflicts, pending/failed outbox rows, call setup latency, transcript latency,
quota counters, and shadow/reconciliation alarms. Logs must contain only IDs,
operation names, and error classes—not contact data, transcript text, API
hashes, credentials, or interpreter-private content.

After securely editing `/etc/finispeak/finispeak.env`, the exact controlled
activation sequence is:

```bash
sudo systemctl restart finispeak.service
curl --fail --silent --show-error http://127.0.0.1:8080/api/ready
sudo journalctl -u finispeak.service --since "5 minutes ago" --no-pager
```

Do not run this sequence until the maintenance window is active, the final
production reconciliation has just passed, and the attestation is less than
30 minutes old. Inspect logs for error classes only; do not paste secrets or
private records into an incident channel.

## Reconciliation and rollback

During MySQL-primary, use MySQL as the durable source. Reconciliation against
the frozen Firestore durable snapshot is diagnostic; never replay Firestore
over newer MySQL mutation versions. Outbox events are committed atomically with
MySQL writes and may be replayed idempotently by aggregate/version.

Rollback is safe only before MySQL has accepted unique durable writes, or after
an explicit reverse-catch-up tool has copied and verified those writes. To
rollback before writes: drain traffic, set the backend to `firestore`, clear the
MySQL-primary activation variables, restart one instance, pass health and API
smoke tests, then restore traffic. If MySQL has accepted writes, keep traffic
drained and escalate; switching flags alone would lose those writes. Never
delete either datastore during rollback.

Before any MySQL-primary durable write, rollback consists of securely setting
`FINISPEAK_REPOSITORY_BACKEND=firestore` and
`FINISPEAK_MYSQL_PRIMARY_ENABLED=false` in
`/etc/finispeak/finispeak.env`, removing the two reconciliation attestation
values, and then using the same one-instance restart and readiness check above.
There is currently no production-approved reverse MySQL-to-Firestore catch-up
tool. Once MySQL has accepted a unique durable write, flag-only rollback is a
stop condition, not a procedure: keep traffic drained and implement and verify
reverse catch-up before returning to Firestore-primary.

The transactional outbox currently provides atomic, privacy-safe mutation
evidence and replay identity. No production dispatcher or retention worker is
implemented. Pending rows are therefore expected to accumulate in
MySQL-primary mode until an operator-approved consumer/retention policy exists;
failed rows are never acceptable. This does not affect MySQL commits, but its
capacity and operational ownership must be accepted before activation.

## Fail-closed conditions

Startup is rejected for incomplete MySQL variables, stale or malformed
reconciliation evidence, a missing schema attestation, shadow mode without its
explicit enable flag, any shadow-write request, or unsafe domain dependencies.
Runtime database failures return errors; the provider does not silently read
stale Firestore data in MySQL-primary mode.
