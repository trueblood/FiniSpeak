# Phase 4–5 MySQL read/write cutover

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
2. Confirm `alembic current` reports `20261013_0002`. Do not run Alembic from
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
FINISPEAK_MYSQL_EXPECTED_REVISION=20261013_0002
FINISPEAK_MYSQL_RECONCILED_AT=<fresh UTC timestamp>
FINISPEAK_MYSQL_RECONCILIATION_DIGEST=<64 lowercase hex characters>
FINISPEAK_SHADOW_COMPARISON_ENABLED=false
FINISPEAK_SHADOW_WRITES_ENABLED=false
```

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

## Fail-closed conditions

Startup is rejected for incomplete MySQL variables, stale or malformed
reconciliation evidence, a missing schema attestation, shadow mode without its
explicit enable flag, any shadow-write request, or unsafe domain dependencies.
Runtime database failures return errors; the provider does not silently read
stale Firestore data in MySQL-primary mode.
