#!/usr/bin/env python3
"""Validate aggregate Firebase Storage migration reports without object data."""

import argparse
import json
from pathlib import Path


ERROR_FIELDS = ("invalid", "missingOwner", "errors", "rolledBack")


def load_report(path):
    lines = [line for line in Path(path).read_text().splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"Storage migration report is empty: {path}")
    report = json.loads(lines[-1])
    for field in ("source", "valid", "existing", "committed", "verified", *ERROR_FIELDS):
        if not isinstance(report.get(field), int) or report[field] < 0:
            raise ValueError(f"Storage migration report has invalid aggregate field: {field}")
    return report


def validate(dry_run, first_apply, replay):
    for report in (dry_run, first_apply, replay):
        if any(report[field] for field in ERROR_FIELDS) or report.get("partial"):
            raise ValueError("Storage migration reported rejected, rolled-back, or partial records.")
        if report["source"] != report["valid"]:
            raise ValueError("Not every source object passed validation.")
    source = dry_run["source"]
    if first_apply["source"] != source or replay["source"] != source:
        raise ValueError("Firebase Storage source count changed during the controlled import.")
    if first_apply["verified"] != source:
        raise ValueError("The first apply did not verify every source object.")
    if replay["verified"] != source or replay["existing"] != source or replay["committed"]:
        raise ValueError("The replay was not fully idempotent.")
    return {
        "source": source,
        "importedOnFirstApply": first_apply["committed"],
        "existingOnReplay": replay["existing"],
        "verifiedOnReplay": replay["verified"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dry_run", type=Path)
    parser.add_argument("first_apply", type=Path)
    parser.add_argument("replay", type=Path)
    args = parser.parse_args()
    result = validate(*(load_report(path) for path in (
        args.dry_run, args.first_apply, args.replay
    )))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
