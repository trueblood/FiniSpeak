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
        "firestore.rules", "storage.rules", "firebase.json", "docs/ACCESSIBILITY_AUDIT.md",
        "docs/COMMERCIAL_API.md", "docs/LANGUAGE_DETECTION.md", "views/templates/index.html",
    ]
    checks["requiredArtifacts"] = all((ROOT / path).exists() for path in required_files)
    rows = [json.loads(line) for line in args.language_dataset.read_text().splitlines() if line.strip()]
    checks["languageEvaluationGate"] = release_gate(evaluate_language_predictions(rows))["passed"]
    if args.production:
        checks.update({
            "firebaseProject": bool(os.getenv("FIREBASE_PROJECT_ID", "").strip()),
            "openAiKey": bool(os.getenv("OPENAI_API_KEY", "").strip()),
            "apiKeyPepper": len(os.getenv("FINISPEAK_API_KEY_PEPPER", "").strip()) >= 32,
            "firebaseWebConfig": all(os.getenv(name, "").strip() for name in ("FIREBASE_WEB_API_KEY", "FIREBASE_AUTH_DOMAIN", "FIREBASE_APP_ID")),
        })
    failed = [name for name, passed in checks.items() if not passed]
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    if failed:
        print(f"\nReadiness failed: {', '.join(failed)}")
        raise SystemExit(1)
    print("\nFiniSpeak readiness checks passed.")


if __name__ == "__main__":
    main()
