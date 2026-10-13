# DigitalOcean MySQL backup and restore runbook

This runbook is for the self-managed MySQL 8 instance used by FiniSpeak. Test
every command on a non-production host first. Backups are not considered valid
until a restore has completed and the restored data has been verified.

## Security requirements

- Use a dedicated backup account with `SELECT`, `SHOW VIEW`, `TRIGGER`, and
  `EVENT` only. Add `RELOAD`, `PROCESS`, or replication privileges only when a
  reviewed backup method actually requires them.
- Put credentials in `/etc/finispeak/mysql-backup.cnf`, owned by root with mode
  `0600`. Never place a password in command arguments, shell history, logs, or
  the repository.
- Write backups to a root-owned directory with mode `0700`, encrypt them before
  off-host transfer, and use a separate encryption key from the database host.
- Retain at least one off-host copy in a private DigitalOcean Spaces bucket or
  another approved backup account. Enable object versioning or retention locks.
- Restrict MySQL to private networking or a host firewall. Require TLS for any
  remote backup or restore connection.
- Treat dumps as highly sensitive: they contain contact details, credential
  metadata, API hashes, and call transcripts.

Example client file structure (values come from the production secret store):

```ini
[client]
host=127.0.0.1
port=3306
user=finispeak_backup
password=REDACTED
ssl-mode=REQUIRED
```

## Full logical backup

1. Confirm disk space, replication/instance health, and the destination path.
2. Capture the deployed Alembic revision and MySQL version in a separate
   metadata file; do not put credentials in it.
3. Use an InnoDB-consistent, streaming dump:

   ```bash
   sudo mysqldump --defaults-extra-file=/etc/finispeak/mysql-backup.cnf \
     --single-transaction --quick --routines --triggers --events \
     --hex-blob --set-gtid-purged=OFF --databases finispeak \
     | gzip -9 > /var/backups/finispeak/finispeak-YYYYMMDDTHHMMSSZ.sql.gz
   ```

4. Generate a SHA-256 checksum, encrypt the dump with the approved backup key,
   upload the encrypted object and checksum off-host, and then remove any
   unencrypted staging copy.
5. Record start/end time, size, checksum, MySQL version, Alembic revision, and
   encrypted object location. Do not record row contents or secrets.

`--single-transaction` provides a consistent snapshot for InnoDB tables without
locking application writes for the duration of the dump. It does not make a
mixed non-InnoDB database consistent; verify every FiniSpeak table uses InnoDB.

## Point-in-time recovery

Logical backups alone can lose changes since the last dump. Enable MySQL binary
logging with a reviewed retention period, encrypt and copy binlogs off-host,
and monitor continuity. Record the binlog coordinates associated with each full
backup. Test replay to a timestamp on a non-production instance at least
quarterly.

## Restore drill

Never test a restore over the live database.

1. Provision a separate MySQL 8 instance with no application traffic.
2. Verify the encrypted object's checksum before decryption.
3. Create a restore-only credentials file with mode `0600`.
4. Restore the dump into the isolated instance:

   ```bash
   gzip -dc /secure/restore/finispeak-YYYYMMDDTHHMMSSZ.sql.gz \
     | mysql --defaults-extra-file=/etc/finispeak/mysql-restore.cnf
   ```

5. If testing point-in-time recovery, apply binlogs only through the selected
   recovery timestamp.
6. Verify:
   - Alembic revision and expected tables/indexes.
   - Exact primary-key counts and sampled canonical field hashes.
   - Foreign keys and orphan checks.
   - Firestore document IDs remain unchanged in MySQL primary keys.
   - API keys remain hashes and no plaintext credential exists.
   - The application test suite against the isolated database.
7. Record recovery point objective, recovery time, verification results, and
   any corrective action. Destroy the temporary restore instance securely when
   the drill is complete.

## Production restore approval

A production restore requires an approved incident procedure: stop or place the
application in maintenance mode, preserve the damaged database for forensics,
restore to a new database when possible, verify it, change the application
connection atomically, and monitor. Do not run Alembic downgrades as a backup
substitute. Do not delete Firestore or use it as an unverified rollback source.

## Recommended schedule

- Nightly encrypted logical backup.
- Continuous encrypted binlog archive for point-in-time recovery.
- Automated checksum and age monitoring on every backup.
- Monthly automated restore validation and quarterly documented recovery drill.
- Retention aligned with the approved transcript, account, and credential-data
  policies; backup retention must not silently exceed privacy requirements.
