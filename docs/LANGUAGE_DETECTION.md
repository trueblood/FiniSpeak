# Language-detection reliability

FiniSpeak treats automatic detection as decision support, not an infallible identity claim.

## Runtime safeguards

- Each connection keeps a bounded rolling evidence window; transcript text and audio are not retained by the tracker.
- Scores combine model confidence, speech length, and sample recency.
- At least two samples and a configurable confidence threshold are required before automatic routing.
- Conflicting or weak evidence prompts participant confirmation.
- Participant confirmation is authoritative and is sent back to transcription for subsequent chunks.
- Code-switching remains visible because each transcript segment retains its raw detected language while the UI also receives a stabilized primary-language estimate.
- Metrics store language codes, confidence, confirmation/correction outcome, sample count, call ID, and timestamp—never transcript text or raw audio.

Configure `LANGUAGE_EVIDENCE_WINDOW`, `LANGUAGE_MINIMUM_SAMPLES`, and `LANGUAGE_CONFIRMATION_THRESHOLD` in the deployment environment.

## Evaluation gate

Export privacy-reviewed prediction rows as JSONL with `expectedLanguage`, `predictedLanguage`, `confidence`, and optional `confirmedLanguage`, then run:

```bash
python scripts/evaluate_language_detection.py evaluation.jsonl --report language-report.json
```

The default release gate requires 90% overall accuracy, 90% coverage, 95% accuracy for high-confidence predictions, and no more than a 10% correction rate. Evaluate every supported language, accents/dialects, short speech, noisy audio, silence, and code-switching separately; aggregate accuracy must not hide a weak language cohort.
