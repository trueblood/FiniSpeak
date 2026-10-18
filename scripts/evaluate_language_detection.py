#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.language_evaluation_service import evaluate_language_predictions, release_gate


def main():
    parser = argparse.ArgumentParser(description="Evaluate recorded FiniSpeak language predictions without transcript audio or text.")
    parser.add_argument("dataset", type=Path, help="JSONL rows with expectedLanguage, predictedLanguage, confidence, and optional confirmedLanguage")
    parser.add_argument("--report", type=Path, help="Optional JSON report output")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    result = release_gate(evaluate_language_predictions(rows))
    output = json.dumps(result, indent=2, sort_keys=True)
    print(output)
    if args.report:
        args.report.write_text(output + "\n")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
