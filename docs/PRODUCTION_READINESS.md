# Production readiness and launch checklist

Status: **code controls implemented; production evidence pending**

This report covers the deployment-ready branch. A launch is approved only when every release-blocking checkbox below has current evidence attached to the release record.

## 1. Accessibility

- [x] Semantic page, form, tab, dialog, status, transcript, and call-control patterns implemented.
- [x] Dialog focus containment/restoration and inert background content implemented.
- [x] Reduced-motion behavior and visible focus treatment implemented.
- [x] Source-level regression gate added in `tests/test_accessibility.py`.
- [ ] Complete keyboard-only testing at 200% zoom in supported browsers.
- [ ] Complete VoiceOver/Safari and NVDA/Chrome passes and record findings.
- [ ] Obtain an independent WCAG 2.2 AA audit before making a contractual conformance claim.

## 2. Commercial API security and operations

- [x] Versioned `/api/v1` surface separated from first-party Firebase APIs.
- [x] One-time API key issuance with keyed hashes; plaintext keys are never stored.
- [x] Scopes, expiration, revocation, atomic minute limits, and daily quotas implemented.
- [x] Request IDs, security headers, usage events, latency/error summaries, and OpenAPI 3.0 documentation implemented.
- [x] Liveness (`/api/health`) and dependency readiness (`/api/ready`) endpoints implemented.
- [ ] Set a unique 32+ byte `FINISPEAK_API_KEY_PEPPER` in the production secret manager.
- [ ] Configure Firestore TTL for counter documents and an approved usage-event retention period.
- [ ] Connect `/api/admin/api-usage` and platform logs to alerts for elevated errors, latency, and quota abuse.
- [ ] Run key issuance, rotation, revocation, and incident-response exercises with a test organization.

## 3. Language-detection reliability

- [x] Bounded multi-sample evidence aggregation implemented without storing audio or transcript text.
- [x] Minimum-sample and confidence thresholds prevent weak automatic routing.
- [x] Participant confirmation/correction is authoritative and measured.
- [x] Per-segment language remains available for multi-language and code-switching calls.
- [x] Privacy-preserving monitoring and administrator summary endpoint implemented.
- [x] Repeatable evaluation and release gate added.
- [ ] Build a consented, representative production evaluation set for every supported language and major audio condition.
- [ ] Pass the gate per language cohort—not only in aggregate—and obtain product/privacy approval of thresholds.
- [ ] Configure alerts for correction rate and low-confidence rate regressions.

## 4. Infrastructure, privacy, and release operations

- [ ] Deploy and acceptance-test Firestore and Storage rules in the Firebase Emulator and production project.
- [ ] Configure TURN for calls that cannot establish direct WebRTC connectivity.
- [ ] Approve transcript consent, retention, deletion, and administrator-access policy.
- [ ] Configure backups, restore drills, secret rotation, least-privilege service accounts, error reporting, dashboards, and paging.
- [ ] Load-test call signaling, transcription concurrency, Firestore quota usage, and commercial API limits.
- [ ] Complete three-account browser acceptance testing in every supported browser/device combination.
- [ ] Confirm privacy policy, terms, incident response, support ownership, and rollback procedure.

## Release commands

```bash
python -m unittest discover -s tests
python scripts/evaluate_language_detection.py evaluation.jsonl --report language-report.json
python scripts/production_readiness_check.py --production --language-dataset evaluation.jsonl
```

The last command intentionally fails if secrets/configuration are absent or the language gate fails. `/api/ready` must return HTTP 200 before production traffic is enabled.
