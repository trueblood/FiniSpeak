#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.language_evaluation_service import evaluate_language_predictions, release_gate
import json


def main():
    parser = argparse.ArgumentParser(description="Run FiniSpeak production-readiness configuration checks.")
    parser.add_argument("--production", action="store_true", help="Require production secrets and service configuration")
    parser.add_argument("--language-dataset", type=Path, default=ROOT / "tests" / "fixtures" / "language_detection_cases.jsonl")
    args = parser.parse_args()
    checks = {}
    required_files = [
        "migrations/versions/20261014_0003_firebase_replacements.py", "migrations/versions/20261016_0004_friends_and_soft_delete.py", "docs/FIREBASE_REMOVAL.md", "docs/ACCESSIBILITY_AUDIT.md",
        "docs/COMMERCIAL_API.md", "docs/LANGUAGE_DETECTION.md", "views/templates/index.html",
    ]
    checks["requiredArtifacts"] = all((ROOT / path).exists() for path in required_files)
    rows = [json.loads(line) for line in args.language_dataset.read_text().splitlines() if line.strip()]
    checks["languageEvaluationGate"] = release_gate(evaluate_language_predictions(rows))["passed"]
    if args.production:
        test_deployment = os.getenv("FINISPEAK_TEST_DEPLOYMENT", "false").strip().lower() == "true"
        checks.update({
            "openAiKey": bool(os.getenv("OPENAI_API_KEY", "").strip()),
            "apiKeyPepper": len(os.getenv("FINISPEAK_API_KEY_PEPPER", "").strip()) >= 32,
            "mysql": all(os.getenv(name, "").strip() for name in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD")),
            "firstPartyAuth": len(os.getenv("FINISPEAK_JWT_SECRET", "").strip()) >= 32,
            "privateStorage": bool(os.getenv("FINISPEAK_STORAGE_ROOT", "").strip()),
            "emailDelivery": all(os.getenv(name, "").strip() for name in ("FINISPEAK_SMTP_HOST", "FINISPEAK_EMAIL_FROM", "FINISPEAK_PUBLIC_URL")),
            "webrtcRelay": bool(os.getenv("FINISPEAK_TURN_URLS", "").strip()) and len(os.getenv("FINISPEAK_TURN_SECRET", "")) >= 32,
            "mysqlOnlyRouting": os.getenv("FINISPEAK_REPOSITORY_BACKEND", "mysql").strip().lower() == "mysql",
            "schemaAttestation": os.getenv("FINISPEAK_MYSQL_EXPECTED_REVISION", "").strip() == "20261016_0004",
        })
    deferred = {"emailDelivery", "webrtcRelay"} if args.production and test_deployment else set()
    failed = [name for name, passed in checks.items() if not passed and name not in deferred]
    for name, passed in checks.items():
        status = "DEFER" if name in deferred and not passed else ("PASS" if passed else "FAIL")
        print(f"{status}  {name}")
    if failed:
        print(f"\nReadiness failed: {', '.join(failed)}")
        raise SystemExit(1)
    print("\nFiniSpeak readiness checks passed.")


if __name__ == "__main__":
    main()
