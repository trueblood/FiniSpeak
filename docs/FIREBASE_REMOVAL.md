# Firebase removal runbook

This codebase is prepared to run without Firebase at application runtime. MySQL
is the only accepted repository backend, authentication is local Argon2id plus
revocable JWT sessions, files are private on-disk objects with MySQL metadata,
and WebRTC signaling is an authenticated MySQL event stream. The Firebase Admin
SDK remains only in `requirements-migration.txt` for read-only retirement tools.

This runbook does not authorize a production change. Do not disable or delete
Firebase until the final verification and retention window have completed.

## Required production services

- MySQL 8 at Alembic revision `20261014_0003`.
- A private directory outside `/var/www/finispeak`, owned by the service account
  with mode `0750`; files are created with mode `0640`.
- SMTP over TLS for verification, activation, and password-reset links.
- A STUN/TURN service (for example a separately secured coturn instance) using
  coturn's shared-secret REST authentication. The API returns one-hour,
  pseudonymous relay credentials; it never exposes the shared secret. TURN over
  UDP and TLS/TCP should be reachable from real client networks.
- Nginx WebSocket proxying for `/ws/signaling` and `/ws/transcription`.

## IP-only preparation milestone

Production preparation may use `206.189.203.96` before a public hostname and
certificate are available. This permits backup/restore drills, private storage
setup, JWT secret generation, migration rehearsal on isolated MySQL databases,
and authenticated signaling tests on the server. It does **not** authorize
weakening `FINISPEAK_COOKIE_SECURE=true` or opening first-party authentication
to public HTTP traffic. Public registration, activation links, password reset,
and the final Firebase-free cutover remain blocked until their secure delivery
and connectivity checks pass.

TURN can initially be prepared for IP-based UDP/TCP on port 3478. TURN over TLS
and port 5349 are deferred with the hostname-dependent TLS work. Do not start or
expose coturn until the firewall change has separate operator approval.

### Restrictive firewall plan (do not apply implicitly)

Keep an existing SSH session open and verify a second SSH connection before
closing it. Review any DigitalOcean cloud firewall together with the host rules
so they do not contradict each other. The intended host policy is:

- default deny incoming and allow outgoing;
- rate-limit TCP 22 for SSH;
- retain TCP 80 while the existing IP-based site is required;
- add TCP 443 only when HTTPS is configured;
- after explicit coturn approval, allow TCP/UDP 3478 and TCP/UDP
  49160–49200 for relays;
- defer TCP 5349 until TURN TLS is configured;
- keep MySQL 3306 private and never expose the Flask/Gunicorn port 8080.

Before enabling the firewall, confirm console recovery access, snapshot the
current rules, run a dry review of the resulting rule list, and ensure the
DigitalOcean control-plane firewall permits the same SSH source. After enabling
it, verify SSH, HTTP, and database privacy from a second connection. Coturn must
remain stopped until its shared-secret configuration and relay range match
these rules.

The complete environment template is `.env.example`. Store real values only in
`/etc/finispeak/finispeak.env`; never copy that file into the release directory.
The production app refuses missing MySQL/JWT settings, rejects `firestore` and
`shadow` repository flags, and reports not-ready if storage, SMTP, TURN, OpenAI,
the API pepper, MySQL, or schema revision checks fail.

For the authorized IP-only test deployment, set
`FINISPEAK_TEST_DEPLOYMENT=true`. This defers only SMTP delivery and public TURN
from the readiness decision; their individual checks remain visible as false.
JWT, secure cookies, private storage, OpenAI, the API-key pepper, MySQL, schema
revision, and all ten MySQL repository routes still fail closed.

## GitHub Actions test deployment

The `Deploy FiniSpeak` workflow stages the exact commit under `/tmp`, runs the
real MySQL 8 integration suite with `MYSQL_DATABASE` forcibly set to
`finispeak_migration_test`, and only then synchronizes the release into
`/var/www/finispeak`. The remote deployment script accepts only the `finispeak`
application database and schema revisions `20261013_0002` or
`20261014_0003`.

On the first successful run it performs this ordered transaction boundary:

1. Create a mode-0600, single-transaction MySQL dump and SHA-256 sidecar under
   `/var/backups/finispeak`, then validate the compressed stream.
2. Apply Alembic `20261014_0003`. The revision adds tables and does not remove
   imported records or Firestore document IDs.
3. Validate Firebase Storage read-only, import into the private storage root,
   and apply again. The second apply must commit zero objects and verify every
   source object as existing.
4. Enforce the service account's ownership, directory mode `0750`, file mode
   `0640`, database ownership, file counts, sizes, and SHA-256 checksums.
5. Run read-only Firestore/MySQL reconciliation. MySQL-native additions made
   after the earlier cutover are permitted, but any missing or content-changed
   imported ID aborts deployment.
6. Atomically update only controlled routing and attestation keys in
   `/etc/finispeak/finispeak.env`, remove runtime Firebase credential pointers,
   restart once, and run loopback authentication, storage authorization,
   deletion, session revocation, signaling, readiness, and routing checks.

Completion markers and aggregate evidence are mode 0600 under
`/var/lib/finispeak/cutover`. Later deployments skip the completed schema and
Storage imports, re-verify files, and create a fresh read-only reconciliation
attestation. Firebase source objects are never modified or deleted. Migration
credentials remain outside the release and are passed only to the two
migration/reconciliation processes; they are not present in the service
process environment.

If the workflow fails before restart, the old process remains running and the
additive `0003` schema is safe for it. If it fails after restart, inspect the
mode-0600 evidence and service log before retrying; do not remove a completion
marker to force an import. Roll back application code only after measuring any
new MySQL/file writes. Do not downgrade the schema or restore the backup over
the live database automatically.

## Back up before changing anything

Configure a restricted MySQL login path interactively so the password does not
appear in process lists or shell history:

```bash
mysql_config_editor set --login-path=finispeak-backup --host=127.0.0.1 --user=finispeak_backup --password
sudo install -d -m 0700 /var/backups/finispeak
sudo sh -c 'umask 077; mysqldump --login-path=finispeak-backup --single-transaction --routines --triggers --set-gtid-purged=OFF finispeak | gzip > /var/backups/finispeak/mysql-pre-firebase-removal.sql.gz'
sudo sh -c 'umask 077; tar --acls --xattrs -C /var/lib/finispeak -czf /var/backups/finispeak/private-files-pre-firebase-removal.tar.gz private-files'
sudo cp --preserve=mode,ownership,timestamps /etc/finispeak/finispeak.env /var/backups/finispeak/finispeak.env.pre-firebase-removal
```

Encrypt and copy backups to a separate access-controlled system. Test restore in
an isolated database and directory. Never restore over production as a test.

## Preparation order

1. Put the site into a documented maintenance window. Keep the current process
   running until every preflight below passes.
2. Create the private storage directory and SMTP/TURN configuration. Test TURN
   from two different networks; STUN alone is insufficient for many callers.
3. Install the migration-only dependencies in a separate admin virtualenv. Keep
   the Firebase service-account file outside the repository and readable only by
   the operator.
4. Copy the new release to a staging/release directory. Do not restart yet.
5. Run `alembic current`, take the backups above, then explicitly run:

   ```bash
   cd /var/www/finispeak
   set -a; . /etc/finispeak/finispeak.env; set +a
   ./venv/bin/alembic upgrade 20261014_0003
   ./venv/bin/alembic current
   ```

   The final command must report exactly `20261014_0003`.
6. Validate legacy Storage without writes, then apply and repeat to prove
   idempotency. Neither command deletes or updates Firebase objects:

   ```bash
   ./migration-venv/bin/python scripts/migrate_firebase_storage.py
   ./migration-venv/bin/python scripts/migrate_firebase_storage.py --apply
   ./migration-venv/bin/python scripts/migrate_firebase_storage.py --apply
   ```

   Require zero invalid objects, missing owners, rollbacks, and errors. On the
   second apply, `committed` must be zero and all eligible objects must be
   reported as existing.
7. Dry-run imported-account activation. Activate an operator account first,
   verify its email/reset/sign-in flow, then send the remaining links. IDs are
   unchanged; Firebase passwords are not copied or logged.

   ```bash
   ./venv/bin/python scripts/send_account_activation.py
   ./venv/bin/python scripts/send_account_activation.py --user-id PRESERVED_USER_ID --apply
   ./venv/bin/python scripts/send_account_activation.py --apply
   ```

8. Confirm Nginx contains the equivalent of:

   ```nginx
   location /ws/ {
       proxy_pass http://127.0.0.1:8000;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
       proxy_set_header Host $host;
       proxy_read_timeout 75s;
   }
   ```

   Run Gunicorn with threaded workers because each WebSocket is long-lived, for
   example `--worker-class gthread --workers 2 --threads 20 --timeout 90`.
   Signaling state is shared through MySQL, so reconnects can land on another
   worker. Events expire after ten minutes and client event IDs are idempotent.
9. Run the complete unit suite and the opt-in MySQL 8 integration suite against
   `finispeak_migration_test` only. The integration test refuses every other
   database name.
10. Set a fresh production reconciliation SHA-256 attestation and timestamp,
    keep all ten repository flags on `mysql`, restart once, and immediately
    check `/api/ready`.

## End-to-end verification

Use two dedicated test accounts that are participants in a disposable active
call. The verifier never prints credentials. Its file write is deleted and its
signaling event expires automatically.

```bash
export FINISPEAK_VERIFY_EMAIL='...'
export FINISPEAK_VERIFY_PASSWORD='...'
export FINISPEAK_VERIFY_PEER_EMAIL='...'
export FINISPEAK_VERIFY_PEER_PASSWORD='...'
export FINISPEAK_VERIFY_CALL_ID='...'
./venv/bin/python scripts/verify_firebase_free.py --base-url https://YOUR_HOST
```

Require every line to say `PASS`. Also verify registration, email verification,
password reset, logout/revocation, profile photo access, private credential
denial for another account, interpreter discovery, a two-network audio/video
call through TURN, transcription, and an application restart. Confirm
`/api/ready` lists all ten repositories as `mysql` and schema `20261014_0003`.

## Rollback

Do not downgrade `0003` during an incident; the added tables are backward-safe.
Stop the new process, restore the previous release, and restore the preserved
environment file. If new first-party writes occurred, rolling back to the old
Firebase application would lose those writes because dual writes are disabled.
Therefore rollback after opening traffic requires either a maintenance window
and an audited forward-copy procedure, or restoring the MySQL/file backup and
accepting the explicitly measured loss window. Never silently switch repository
flags to Firestore; the code rejects that configuration.

If the schema change itself must be undone before any new traffic, restore the
pre-change MySQL backup into an isolated database, verify it, then schedule a
separate restore. Restore private files from the matching encrypted archive so
database metadata and object content remain consistent.

## Firebase shutdown gate

Keep Firebase read-only and billed through the agreed retention period. Only
after repeated verification and backup restores may an operator separately:

1. archive final Auth/Firestore/Storage exports;
2. revoke Firebase service-account credentials;
3. remove the migration virtualenv and legacy Firebase environment values;
4. disable Firebase products and then the related Google Cloud billing.

Those actions are intentionally not automated by this repository.
