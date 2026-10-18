# Phase 3 Firestore-primary MySQL synchronization

Phase 3 is an operator-run, opt-in mirror. Firestore remains authoritative and
the application still reads and writes only Firestore. Importing the code or
starting Flask does not start synchronization.

## Safety gates

Both flags default to off:

- `FINISPEAK_FIRESTORE_MYSQL_SYNC_ENABLED`
- `FINISPEAK_FIRESTORE_MYSQL_SYNC_DELETIONS_ENABLED`

An apply run requires the first flag and `--apply`. Deletions require both
flags, `--apply`, `--apply-deletions`, and two consecutive complete scans that
observe the same MySQL ID missing from Firestore. Do not put these flags in the
production web service environment; give them only to an approved, separately
scheduled synchronization job.

Deletion synchronization also requires `FIREBASE_PROJECT_ID`, and the tool
rejects a Firestore client that reports a different project.

The synchronizer never writes to Firestore. It does not change Firebase Auth,
security rules, Storage, realtime listeners, WebRTC signaling, or API traffic.

## How synchronization works

Every run performs a complete Firestore snapshot of the durable migration
collections in dependency order. This is intentional: account/profile,
taxonomy, transcript, and signaling-adjacent browser changes do not pass
through Flask, so backend-only dual writes would miss them.

For each document, the mirror:

1. preserves the exact Firestore document ID and nested parent ID;
2. converts the document using the same validated mapping as the original
   importer and retains unknown fields in `raw_document`;
3. derives an idempotency key from collection, parent/document IDs, Firestore
   update time, and canonical content hash;
4. compares Firestore update time with `source_updated_at` and applies only a
   newer mutation;
5. increments `mutation_version`, records `last_mutation_id`, and advances the
   collection checkpoint in the same MySQL transaction;
6. records a metadata-only, already-processed outbox audit row in that same
   transaction. It is never queued as a reverse write to Firestore.

Retries use bounded exponential backoff and roll back the record, checkpoint,
tombstone, and outbox together. Exhausted retries record only the exception
class in checkpoint telemetry. A duplicate mutation is ignored. An older mutation is marked stale. Two distinct
mutations with the same observed timestamp are marked as an ordering conflict
for reconciliation rather than choosing one silently.

## Existing snapshot and catch-up procedure

Run this first against an isolated restoration of MySQL 8:

```bash
python -m scripts.sync_firestore_to_mysql
python -m scripts.reconcile_firestore_mysql
```

The first command is a read-only plan unless `--apply` is present. The
reconciliation command is always read-only and exits nonzero for any missing,
extra, or content-mismatched record.

After backup/restore validation and explicit approval, the catch-up sequence is:

1. Set only `FINISPEAK_FIRESTORE_MYSQL_SYNC_ENABLED=true` for the isolated sync
   process and run `python -m scripts.sync_firestore_to_mysql --apply`.
2. Run reconciliation. Investigate conversion, relationship, ordering, and
   content mismatches without printing private values.
3. Run another complete apply scan. This captures direct browser writes that
   arrived during or after the one-time import and records the first deletion
   candidate set.
4. Run at least one further complete scan. Only after reviewing both scans may
   deletion handling be enabled for the isolated job and run with
   `--apply --apply-deletions`.
5. Repeat apply plus reconciliation until counts, IDs, and hashes match. Stop
   rather than accepting unexplained drift.

Rows from the original import have no reliable `source_updated_at`. The first
Phase 3 scan therefore advances them to a new mutation version using the
Firestore snapshot update time. Replaying that snapshot is idempotent.

## Deletion and ordering limitations

Firestore snapshot queries do not provide a durable deletion log. An absent
document may reflect a deletion, a transient failed/partial scan, permissions,
or querying the wrong project. The tool therefore:

- advances deletion candidates only after a complete scan and zero upsert
  errors;
- requires the same absence in two consecutive successful scans;
- deletes nested records before parents;
- records a tombstone transactionally with the delete;
- rejects later stale snapshots whose update time precedes the tombstone;
- permits intentional recreation only with a newer Firestore update time.

Because Firestore has no global cross-document ordering guarantee, checkpoints
are collection-level operational watermarks, not a total order. Ordering is
enforced per record. Nested participant, review, and transcript documents have
independent timestamps. A full scan plus reconciliation is required after any
interruption.

The deletion time is the confirming scan time, not the unknowable original
Firestore delete time. For stronger guarantees, a future client/API phase must
write durable deletion events before deleting documents.

## Reconciliation and sensitive data

Reconciliation compares:

- source and target counts;
- exact primary-key sets, including nested parent/document keys;
- SHA-256 hashes of canonical Firestore content versus MySQL `raw_document`.

MySQL-only metadata—migration timestamps, mutation versions, checkpoints,
tombstones, generated columns, and outbox state—is intentionally excluded.
Logs contain counts and short one-way identifier fingerprints only. They never
contain contact details, private interpreter documents, credentials, API-key
hashes, transcript text, or document payloads.

`emailDirectory` remains intentionally outside the mirror because it is a
derived PII lookup that will be replaced from canonical users. WebRTC connection
documents and ICE candidate subcollections remain excluded because they are
ephemeral signaling state.

## Rollback

Stop the isolated synchronization job and remove its two enable flags. The web
application needs no rollback because it never switched away from Firestore.

For a failed MySQL mirror run, retain the error counts, restore the pre-run
MySQL backup in the isolated environment, and rerun from a full Firestore scan.
Do not downgrade `0002` after synchronization state exists: that downgrade
removes checkpoints, tombstones, mutation metadata, and outbox audit history.
Never delete Firestore data as part of rollback.
