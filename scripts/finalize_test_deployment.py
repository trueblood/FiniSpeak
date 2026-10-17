#!/usr/bin/env python3
"""Atomically record a verified test deployment without exposing env values."""

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


KEY = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=")
REPOSITORY_DOMAINS = (
    "accounts", "translators", "calls", "participants", "transcripts",
    "reviews", "organizations", "api_access", "taxonomy", "language_metrics",
)


def update_environment(path, attestation_path, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full lowercase Git commit SHA is required.")
    attestation = Path(attestation_path).read_bytes()
    if not attestation:
        raise ValueError("The deployment attestation is empty.")
    digest = hashlib.sha256(attestation).hexdigest()
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    updates = {
        "FINISPEAK_ENV": "production",
        "FINISPEAK_TEST_DEPLOYMENT": "true",
        "FINISPEAK_COOKIE_SECURE": "true",
        "FINISPEAK_REPOSITORY_BACKEND": "mysql",
        "FINISPEAK_MYSQL_PRIMARY_ENABLED": "true",
        "FINISPEAK_MYSQL_EXPECTED_REVISION": "20261016_0004",
        "FINISPEAK_MYSQL_RECONCILED_AT": timestamp,
        "FINISPEAK_MYSQL_RECONCILIATION_DIGEST": digest,
        "FINISPEAK_SHADOW_COMPARISON_ENABLED": "false",
        "FINISPEAK_SHADOW_WRITES_ENABLED": "false",
        "FINISPEAK_DEPLOYED_COMMIT": commit,
    }
    updates.update({
        f"FINISPEAK_REPOSITORY_{domain.upper()}": "mysql"
        for domain in REPOSITORY_DOMAINS
    })
    remove = {"FIREBASE_CREDENTIALS", "GOOGLE_APPLICATION_CREDENTIALS"}
    source = Path(path)
    original = source.read_text().splitlines()
    output, written = [], set()
    for line in original:
        match = KEY.match(line)
        name = match.group(1) if match else None
        if name in remove:
            continue
        if name in updates:
            if name not in written:
                output.append(f"{name}={updates[name]}")
                written.add(name)
            continue
        output.append(line)
    for name, value in updates.items():
        if name not in written:
            output.append(f"{name}={value}")
    metadata = source.stat()
    descriptor, temporary = tempfile.mkstemp(prefix=".finispeak.env.", dir=source.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write("\n".join(output) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, metadata.st_mode & 0o777)
        os.chown(temporary, metadata.st_uid, metadata.st_gid)
        os.replace(temporary, source)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"commit": commit, "attestationSha256": digest, "attestedAt": timestamp}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-file", default="/etc/finispeak/finispeak.env")
    parser.add_argument("--attestation-file", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    print(json.dumps(update_environment(
        args.environment_file, args.attestation_file, args.commit
    ), sort_keys=True))


if __name__ == "__main__":
    main()
