# FiniSpeak Web MVP

> **Current architecture:** MySQL 8 is the only application data backend.
> FiniSpeak now uses first-party Argon2id/JWT authentication, private
> DigitalOcean file storage, and authenticated MySQL-backed WebRTC signaling.
> The Firebase-era setup notes below are retained only as historical migration
> context and must not be used for a new deployment. Follow
> [`docs/FIREBASE_REMOVAL.md`](docs/FIREBASE_REMOVAL.md) and `.env.example` for
> current setup, verification, rollback, and retirement steps.

FiniSpeak is being built web-first with a MySQL/WebRTC architecture that can later be reused by native iOS (SwiftUI) and Android (Kotlin/Compose) clients.

## MVC architecture

The Flask backend follows an MVC structure while keeping routing and external services explicit:

- `models/` defines the SQL data model.
- `controllers/` validates requests, coordinates models/services, and builds responses.
- `views/templates/` contains server-rendered HTML views.
- `views/static/` contains the view layer's CSS and browser JavaScript.
- `routes/` maps URLs to controllers and contains no business or database logic.
- `services/` integrates first-party authentication, transcription, and other external systems.
- `app.py` is the application factory and dependency-wiring entry point.

Open `/api` or `/api/routes` while the app is running to see the current route catalog. Run the MVC regression tests with:

```bash
python -m unittest discover -s tests
```

## Current MVP

- First-party Email/Password Authentication
- Customer and Translator account roles
- MySQL user profiles and call records
- Customer 1 creates a call to Customer 2 by FiniSpeak email
- Translator can join the existing call as participant #3
- Browser camera/microphone access
- Three-person WebRTC mesh signaling through the authenticated Flask signaling service
- Mute, camera, request translator, copy Call ID, and end-call controls
- STUN configured for development; TURN is intentionally deferred
- Private DigitalOcean-hosted storage for interpreter profile photos
- Interpreter onboarding with draft, profile-complete, submitted, changes-requested, rejected, and verified states
- Private credential evidence uploads with interpreter view/remove controls and administrator review
- Location-aware interpreter discovery with Leaflet, marker clustering, approximate public service areas, map/list/split views, radius filtering, and remote-video fallback

## Interpreter discovery map

The directory supports Nearby, Remote, and Both search modes. Browser coordinates are used only for the active search request and are not written to Firestore. Interpreter profiles may publish an approximate city/region centroid only after the interpreter enables **Show on map**; residential addresses are rejected.

Public interpreter fields added by this feature:

- `serviceLocation`: `city`, `state`, `country`, rounded `latitude`/`longitude`, `geohash`, and `showOnMap`
- `serviceOptions`: `inPerson`, `remote`, and `radiusMiles`

Deploy the included composite indexes before enabling geographic traffic. OpenStreetMap development tiles are the default. For production volume, configure a commercial/provider-hosted tile URL and its required attribution:

```env
MAP_TILE_URL=https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png
MAP_TILE_ATTRIBUTION=&copy; OpenStreetMap contributors
GEOCODING_BASE_URL=https://nominatim.openstreetmap.org/search
GEOCODING_USER_AGENT=FiniSpeak/1.0 (support@finispeak.com)
```

Replace the example geocoding contact with a monitored address and review the chosen provider's production rate/usage terms. Existing interpreter documents remain compatible; interpreters opt into map visibility when they next update their profiles.

## Run locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open http://127.0.0.1:5050

## Firebase setup

1. Create/register a Firebase Web App.
2. Enable Authentication > Email/Password.
3. Create Cloud Firestore.
4. Copy the Firebase web configuration values into `.env`.
5. Publish `firestore.rules` for MVP testing. The call update rule is deliberately broad for development and must be tightened before production.

The optional, parallel MySQL migration preparation is documented in [`docs/MYSQL_MIGRATION.md`](docs/MYSQL_MIGRATION.md). It does not replace Firebase application behavior or run automatically.

## Interpreter profile photos

Create Firebase Storage in **production mode** and set `FIREBASE_STORAGE_BUCKET`
to the bucket shown in Firebase. Profile photos are uploaded to
`interpreter-profiles/{userId}/profile.{jpg|png|webp}` and the download URL is
saved in the interpreter's Firestore profile. Uploads are limited to JPG, PNG,
or WebP images smaller than 5 MB.

Deploy both rule files after Storage is created:

```bash
firebase deploy --only firestore,storage --project finispeak
```

## Interpreter onboarding and verification

Interpreters can save an incomplete draft, save a complete profile, or submit a complete profile and credential evidence for administrator review. Submission requires a name, bio, language, specialty, years of experience, valid weekly availability, at least one credential, and at least one credential document. Administrators can approve the profile or request changes. Approved profiles become visible in discovery; a returned profile can be edited and submitted again.

Credential files are private under `interpreter-credentials/{userId}/`. Interpreters can view or remove their own files. To replace a file, remove it, choose the replacement, and save or resubmit the profile.

For local testing, create three accounts in separate browser profiles/incognito contexts: Customer 1, Customer 2, and Translator. Customer 1 creates a call using Customer 2's email address. Customer 2 joins using the Call ID. Press Request Translator, then the Translator joins using the same Call ID.

## Deployment-ready branch

The `deployment-ready` branch includes the current web MVP plus the production code foundations that do not depend on the pending DigitalOcean infrastructure:

- Call creation, state transitions, interpreter requests, and interpreter claims go through authenticated API endpoints and transactional server-side logic.
- Public interpreter documents are separated from private contact and credential evidence data in `interpreterPrivate/{userId}`.
- Public profile detail endpoints return verified interpreters only, and public profiles include moderated recent reviews.
- Customers can submit a review from completed-call history; administrators can moderate reviews.
- Administrators can create and update organization records, alongside account, interpreter, session, and review oversight.
- `/api/openapi.json`, security response headers, Firestore indexes, and a deployment regression-test gate are included.

Before enabling production traffic, complete the Firebase Emulator/rules acceptance pass, browser acceptance testing with three real accounts, transcript consent/retention review, and the DigitalOcean networking/TURN work when that infrastructure is available. Billing, push notifications, abuse controls, and native mobile incoming-call behavior remain intentionally outside this branch's infrastructure scope.

For Google Cloud Run, build and deploy the existing container, then publish Firestore rules and indexes:

```bash
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/finispeak/web
gcloud run deploy finispeak --image REGION-docker.pkg.dev/PROJECT/finispeak/web --region REGION --allow-unauthenticated
firebase deploy --only firestore:rules,firestore:indexes,storage --project PROJECT
```

Set the existing Firebase/OpenAI environment values plus the map/geocoder values above on the Cloud Run service. Grant its runtime service account Firestore and Storage access through least-privilege IAM.

Production-hardening controls and the remaining evidence checklist are documented in [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md). Commercial API operations are in [`docs/COMMERCIAL_API.md`](docs/COMMERCIAL_API.md), the internal accessibility audit is in [`docs/ACCESSIBILITY_AUDIT.md`](docs/ACCESSIBILITY_AUDIT.md), and language reliability/evaluation is in [`docs/LANGUAGE_DETECTION.md`](docs/LANGUAGE_DETECTION.md).

Run the static readiness gate locally with `python scripts/production_readiness_check.py`. In the deployed environment, use `python scripts/production_readiness_check.py --production --language-dataset <approved.jsonl>` and require `/api/ready` to return HTTP 200 before routing traffic.

To migrate legacy interpreter documents that still contain private fields, preview first and then apply the migration with the production Firebase credentials:

```bash
python scripts/migrate_interpreter_privacy.py --dry-run
python scripts/migrate_interpreter_privacy.py --apply
```


## Customer lookup

For the MVP, FiniSpeak uses first-party email/password authentication and customer-to-customer calling by a saved FiniSpeak email address or phone number. Lookup goes through authenticated server routes backed by MySQL without exposing the full private user profile.


## Legacy migration material

Older Firebase-era files and notes remain in the repository only for migration verification and rollback history. The running application fails closed if a Firebase repository backend is selected; new application work must use the first-party APIs and MySQL repositories.

## Live transcription logging

FiniSpeak transcribes each participant independently for logging: Customer 1, Customer 2, and the Translator. Each browser sends a copy of only its own microphone as PCM16 to `/ws/transcription`. The WebRTC call remains independent, so a transcription failure does not interrupt the call. This pipeline does not machine-translate speech.

Raw microphone chunks are held only in memory long enough to transcribe and are not saved. Final text segments are written through the authenticated transcript API into MySQL and all participants see them in the live transcript panel.

Install the new dependencies with:

```bash
pip install -r requirements.txt
```

The WebSocket verifies the first-party session and call membership. Baseline is the production default. Authorized testers listed in `FINISPEAK_PROCESSING_TESTER_UIDS` can compare Concurrent and Streaming from the call screen; the selection is stored per participant, not globally. Optional transcription settings:

```env
OPENAI_TRANSCRIPTION_MODEL=gpt-transcribe
TRANSCRIPTION_CHUNK_SECONDS=5.0
FINISPEAK_PROCESSING_TESTER_UIDS=user-id-1,user-id-2
CONCURRENT_TRANSCRIPTION_WORKERS=2
STREAMING_TRANSCRIPTION_CHUNK_SECONDS=1.5
TRANSCRIPTION_ESTIMATED_USD_PER_MINUTE=0
```

Concurrent keeps microphone capture running while background workers process complete chunks. Streaming uses shorter server chunks and shows browser speech-recognition partials where supported, while only finalized server results are saved. During a mode change, the prior pipeline drains, new microphone frames are buffered, and the next pipeline receives that buffer without replacing the WebRTC connection.

For local testing, start the app with a local MySQL database (or the development SQLite fallback), sign in with a user ID included in `FINISPEAK_PROCESSING_TESTER_UIDS`, and start a call from `http://localhost:8080`. Select either experimental mode before the call, or switch while connected. Development diagnostics are shown only on localhost.

## Dashboard, incoming calls, and transcript history

Authenticated users are routed to their dashboard. Customers receive a MySQL-backed incoming-call popup with Accept/Decline instead of manually entering a Call ID. Translators receive interpretation-request popups and can join the existing three-person call. The dashboard also loads previous calls for the signed-in participant and opens saved transcript records in a transcript viewer.
