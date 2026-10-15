# Firestore to MySQL migration preparation (historical)

> The application cutover is complete. Use `docs/FIREBASE_REMOVAL.md` for the
> current first-party authentication, private storage, signaling, and deployment
> procedure. The material below documents earlier migration phases only.

This phase creates a parallel MySQL 8 copy only. Firebase Authentication and every application read/write path remain unchanged. The importer never writes to or deletes from Firestore, and no migration runs during application startup or deployment.

Phase 0 operational schema preparation is revision `20261013_0002`. It adds
mutation metadata, synchronization checkpoints, tombstones, a transactional
outbox, non-unique normalized-email lookup, and operational indexes. Deploying
application code alone does not apply this revision or change the authoritative
repository: every repository feature flag defaults to Firestore. Review the
[DigitalOcean backup and restore runbook](DIGITALOCEAN_MYSQL_BACKUP_RESTORE.md)
before scheduling the revision in a separately approved maintenance window.

The normalized-email index is intentionally non-unique. Before proposing a
future uniqueness revision, run a read-only collision count against a restored
production backup and investigate any nonzero result in a restricted workspace:

```sql
SELECT COUNT(*) AS collision_groups
FROM (
  SELECT LOWER(TRIM(email)) AS normalized_email
  FROM users
  WHERE email IS NOT NULL AND TRIM(email) <> ''
  GROUP BY LOWER(TRIM(email))
  HAVING COUNT(*) > 1
) AS collisions;
```

Normalized email values are contact data; do not print collision details into
general deployment logs.

## Phase 1 repository seam

Phase 1 adds storage-independent contracts in `repositories/interfaces.py`
and explicit-session MySQL implementations in `repositories/mysql.py`. They
return the existing Firestore-shaped dictionaries so later controller adoption
does not require an API contract change.

Phase 1 deliberately contains no runtime repository selection. Existing models
and controllers still call Firestore directly, and every repository flag still
defaults to `firestore`. Setting a flag remains diagnostic only and does not
route reads or writes to MySQL.

Before wiring any domain, exercise its repository against an isolated restored
database and compare results with Firestore for authorization, missing records,
ordering, nested values, and legacy documents. Firebase Authentication,
realtime call signaling, WebRTC, Cloud Storage, and Firebase security rules are
outside this repository seam.

Phase 2 routes backend application-data access through Firestore repository
adapters and fails closed if a non-Firestore runtime provider is requested. See
[the Phase 2 integration inventory](PHASE_2_REPOSITORY_INTEGRATION.md) for the
remaining browser/realtime dependencies and later cutover order.

Phase 3 adds an opt-in, operator-run Firestore-primary snapshot mirror and a
read-only canonical reconciliation tool. It remains disabled by default and is
documented in [the Phase 3 synchronization runbook](PHASE_3_FIRESTORE_MYSQL_SYNC.md).

## Source inventory

Firestore document IDs are stored unchanged as MySQL primary keys. Unknown legacy fields are retained in `raw_document` JSON so an unexpected field is not silently discarded.

| Firestore source | Observed fields and structures | MySQL table |
| --- | --- | --- |
| `users` | `uid`, `displayName`, `email`, `phone`, `phoneNormalized`, `role`, `status`, `createdAt`, `updatedAt` | `users` |
| `translators` | `uid`, `displayName`, `bio`, `languages[]`, `dialects[]`, `specialties[]`, `credentials[]`, `yearsExperience`, `photoUrl`, `rating`, `ratingCount`, `onboardingStatus`, `verificationStatus`, `credentialStatus`, `verifiedBy`, `verifiedAt`, `createdAt`, `updatedAt`; `availability{days[],start,end,availableNow,timezone}`; `serviceLocation{city,state,country,latitude,longitude,geohash,showOnMap}`; `serviceOptions{inPerson,remote,radiusMiles}` | `translators` |
| `interpreterPrivate` | `uid`, `email`, `phone`, `credentialDocuments[{name,path,contentType,size,uploadedAt}]`, `verificationNotes`, `verifiedBy`, `verifiedAt`, `createdAt`, `updatedAt` | `interpreter_private` |
| `calls` | `callerId`, `callerName`, `receiverId`, `receiverName`, `translatorId`, `translatorName`, `status`, `translationStatus`, `language`, `detectedLanguage`, `detectedLanguageConfidence`, `requestedLanguages[]`, `dialect`, `specialty`, `purpose`, `recommendedTranslatorIds[]`, `routingStatus`, `scheduledAt`, `createdAt`, `updatedAt`, `startedAt`, `endedAt` | `calls` |
| `calls/{id}/participants` | document ID/`uid`, `role`, `displayName`, `joinedAt`; legacy-safe nullable `leftAt`, `microphoneEnabled`, `cameraEnabled` | `participants` |
| `translators/{id}/reviews` | `authorId`, `authorName`, `callId`, `rating`, `text`, `moderationStatus`, `createdAt` | `reviews` |
| `organizations` | `name`/legacy `displayName`, `contactEmail`, `domain`, `status`, `notes`, `createdBy`, `createdAt`, `updatedAt` | `organizations` |
| `apiKeys` | `organizationId`, `name`, `tokenHash`, `prefix`, `scopes[]`, `minuteLimit`, `dailyQuota`, `status`, `createdBy`, `revokedBy`, `createdAt`, `updatedAt`, `expiresAt`, `lastUsedAt`, `revokedAt` | `api_keys` |
| `apiUsageCounters` | `keyId`, `organizationId`, `kind`, `bucket`, `count`, `updatedAt`, `expiresAt` | `api_usage_counters` |
| `apiUsageEvents` | `keyId`, `organizationId`, `endpoint`, `method`, `statusCode`, `durationMs`, `requestId`, `createdAt` | `api_usage_events` |
| `languageDetectionMetrics` | `callId`, `eventType`, `detectedLanguage`, `confidence`, `confirmedLanguage`, `corrected`, `sampleCount`, `createdAt` | `language_detection_metrics` |
| `reference_languages` | `name`, `nameLower`, `active`, `seeded`, optional `createdBy`, `createdAt` | `reference_languages` |
| `reference_dialects` | same reference-item shape | `reference_dialects` |
| `reference_specialties` | same reference-item shape | `reference_specialties` |

The inventory also found durable `calls/{id}/transcripts` documents. They contain `speakerId`, `speakerRole`, `speakerName`, detected and primary language/confidence fields, `languageSampleCount`, `languageConfirmationRequired`, `text`, `isFinal`, `createdAt`, and browser `clientCreatedAt`. They are prepared in the additional `transcripts` table to prevent future transcript loss.

`emailDirectory` is an additional top-level collection keyed by normalized email. It duplicates `uid`, `displayName`, `role`, `email`, and `updatedAt` from `users`. It is intentionally not copied in phase one: it is PII-bearing lookup material that can be rebuilt from `users`, and the live browser still depends on Firestore for it.

WebRTC `calls/{id}/connections` documents and their per-user ICE candidate subcollections are intentionally not migrated. They are short-lived signaling state; moving them would change live-call behavior.

## Authentication and relationship constraints

Firebase Authentication remains authoritative. Firebase Auth UIDs are preserved as user IDs and foreign keys. The API continues to verify Firebase ID tokens and reads `users.role`/`users.status` from Firestore. No JWT behavior was introduced despite the installed compatibility dependency.

Important relationships include translator-to-user (same Firebase UID), private-profile-to-translator, call caller/receiver/translator, participant-to-call/user, review-to-interpreter/call/author, API key-to-organization, usage-to-key/organization, and metric/transcript-to-call.

Before an apply run, resolve any Firestore orphans that violate those relationships. Do not weaken constraints merely to make a production import pass.

## Risks and safeguards

- Firestore documents are schemaless and may contain legacy or mixed-type values. Known nullable fields are nullable in MySQL; arrays/maps use JSON; unknown fields remain in `raw_document`.
- Firestore timestamps, timezone-aware Python datetimes, ISO strings, and browser epoch milliseconds are normalized to UTC. Unparseable values fail preflight instead of being silently replaced.
- MySQL `DATETIME` does not retain an offset. All migrated values must be interpreted as UTC.
- Credential metadata, contact information, API-key hashes, and transcript text are migrated but never included in migration logs. Protect the MySQL database and backups accordingly.
- A changing Firestore dataset can cause count mismatches. Run a dry run, schedule a controlled final copy window, rerun idempotently, and require count verification before any later cutover.
- The review uniqueness constraint reflects current application behavior: one review per interpreter/call/author. Resolve legacy duplicates before applying.
- The importer uses upserts and does not delete MySQL rows that disappeared from Firestore. Deletion reconciliation requires a separately reviewed process.

## Prepare MySQL on DigitalOcean

1. Back up MySQL and verify a restore on a non-production host.
2. Create a least-privilege database/user. Store all five `MYSQL_*` values in the server's protected service environment; never commit them.
3. Install requirements in the existing virtual environment.
4. Preview SQL without applying it:

   ```bash
   alembic upgrade 20261013_0001 --sql > /tmp/finispeak-mysql-initial.sql
   ```

5. Review the SQL, then explicitly apply the schema during an approved maintenance window:

   ```bash
   alembic upgrade 20261013_0001
   ```

6. Run the read-only preflight and review conversion, required-field, string-length, and relationship errors:

   ```bash
   python -m scripts.migrate_firestore_to_mysql --dry-run --batch-size 250
   ```

7. Only after approval, copy data idempotently:

   ```bash
   python -m scripts.migrate_firestore_to_mysql --apply --batch-size 250
   ```

Dry run reports Firestore source counts and existing MySQL target counts separately. An empty target is expected before the first import and does not fail preflight. Verification compares the exact source primary-key set with MySQL, so unrelated existing target rows do not hide missing imports.

An apply run stops before writing when preflight finds invalid records or missing parents. Batches are transactional; a failed batch is rolled back and every record in it is retried individually. The final summary reports successful commits, rolled-back batch records, retries, failed records, missing IDs, and whether the result is partial. Re-running updates the same primary keys rather than creating duplicates.

## Rollback

This phase has no application cutover, so application rollback is simply to stop migration work; FiniSpeak continues using Firebase Auth and Firestore. Do not delete or disable Firebase.

If the MySQL copy must be discarded, restore the pre-migration MySQL backup or—only with explicit approval and after confirming no MySQL application writes exist—run `alembic downgrade base`. Downgrade drops the prepared MySQL tables and is destructive to the copy, but it never changes Firestore. Preserve importer logs containing counts only and record the failed revision before retrying.

The Firebase replacement preparation is revision `20261014_0003`; see
`docs/FIREBASE_REMOVAL.md` before applying it. It is never run automatically.
