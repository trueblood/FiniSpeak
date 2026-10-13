# Phase 2 repository integration and direct-Firestore inventory

Phase 2 makes the backend repository-aware without changing its active data
provider. `create_app()` constructs only Firestore adapters. Any `mysql` or
`shadow` runtime repository flag fails startup; the Phase 1 MySQL classes are
not connected to live routes and no dual write exists.

## Backend inventory and integration

| Domain | Backend consumers | Phase 2 provider |
| --- | --- | --- |
| Accounts | account routes, call receiver lookup, Firebase-auth profile/status lookup, admin activity | Firestore account adapter |
| Translators | public profiles, discovery, routing, availability, verification, commercial API, admin metrics | Firestore translator adapter |
| Calls | call routes, routing updates, admin metrics, WebSocket participant authorization | Firestore call adapter; existing Firestore transactions retained |
| Sessions/participants | session list/create/state and participant routes | Firestore session and participant adapters |
| Transcripts | no Flask HTTP route; browser writes and listens directly | Firestore transcript adapter prepared but not routed |
| Reviews | public review routes, moderation, admin activity | Firestore review adapter |
| Organizations | admin organization routes and activity | Firestore organization adapter |
| API access | commercial authentication/quota, admin API-key and usage routes, response usage logging | Firestore API-access adapter; quota transaction retained |
| Taxonomy | public taxonomy route | Firestore taxonomy adapter |
| Language metrics | transcription reliability writes and admin summary | Firestore metrics adapter; background write behavior retained |

The API health/readiness controller still performs a direct bounded Firestore
connectivity probe. Firebase initialization and ID-token verification remain in
the authentication service. These are infrastructure/authentication concerns,
not application data-provider bypasses.

## Browser and mobile-style direct Firestore dependencies

No separate native iOS or Android source tree is present in this repository;
the responsive web client is the only checked-in client implementation.

The current web client still uses Firebase directly for the following:

- account signup, legacy profile repair, `users`, and `emailDirectory` writes;
- profile reads and profile/contact updates;
- translator onboarding, public/private profile batches, credential metadata,
  and taxonomy creation;
- call and participant realtime listeners;
- incoming-call and interpreter-request realtime queries;
- durable transcript writes, live transcript listeners, and history reads;
- WebRTC offer/answer documents and ICE-candidate subcollections;
- Firebase Storage uploads/deletions for interpreter photos and credentials.

Two writes that already had equivalent authenticated APIs were moved safely:
the dashboard availability toggle now uses `PATCH /api/availability`, and call
participant creation uses `POST /api/sessions/{id}/participants`. Both APIs
still write to Firestore, so existing realtime listeners continue to receive
the same document changes.

Transcript writes, listeners, participant listeners, incoming-call listeners,
and WebRTC signaling remain direct. Moving them before a replacement realtime
transport exists would break live calls. Firebase Auth and Storage also remain
unchanged.

## Later migration order

1. Add authenticated, validated account bootstrap/profile APIs that update
   `users` and `emailDirectory` atomically; migrate signup repair only after
   compensating behavior for Firebase Auth creation failures is designed.
2. Add translator onboarding APIs with explicit public/private field allowlists
   and signed or server-mediated Storage metadata handling.
3. Add administrator-controlled taxonomy mutation endpoints and stop client
   taxonomy writes.
4. Add transcript append/history APIs with participant authorization, replay
   ordering, idempotency keys, and privacy/retention controls. Keep the live
   Firestore listener until an equivalent stream is deployed.
5. Introduce shadow reads and comparison telemetry one domain at a time. Never
   include contact data, transcript text, credentials, tokens, or API hashes in
   mismatch logs.
6. Only after shadow verification, add outbox-backed dual writes, reconciliation,
   rollback checkpoints, and per-domain canaries. Realtime signaling should be
   the last Firestore application dependency considered for replacement.

Before any provider change, test against an isolated production-data restore,
verify authorization and missing-record parity, and retain a Firestore rollback
path. Do not disable Firebase, security rules, Storage, FCM, or Google Cloud
billing during these phases.
