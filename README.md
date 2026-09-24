# FiniSpeak Web MVP

FiniSpeak is being built web-first with a shared Firebase/WebRTC architecture that can later be reused by native iOS (SwiftUI) and Android (Kotlin/Compose) clients.

## Current MVP

- Firebase Email/Password Authentication
- Customer and Translator account roles
- Firestore user profiles
- Customer 1 creates a call to Customer 2 by FiniSpeak email
- Translator can join the existing call as participant #3
- Browser camera/microphone access
- Three-person WebRTC mesh signaling through Firestore
- Mute, camera, request translator, copy Call ID, and end-call controls
- STUN configured for development; TURN is intentionally deferred
- Firebase Storage and FCM are intentionally deferred

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

For local testing, create three accounts in separate browser profiles/incognito contexts: Customer 1, Customer 2, and Translator. Customer 1 creates a call using Customer 2's email address. Customer 2 joins using the Call ID. Press Request Translator, then the Translator joins using the same Call ID.

## Production work still required

Add TURN/coturn, stricter Firestore security rules, server-authoritative call state, translator discovery/availability, billing, push notifications, verification, abuse controls, and mobile incoming-call behavior before production use.


## Customer lookup

For the MVP, FiniSpeak uses email/password authentication and customer-to-customer calling by FiniSpeak email address. Each new account creates a small `emailDirectory` entry so another signed-in customer can find the intended receiver without exposing the full private user profile. Phone-number calling can be added later for the native iOS and Android apps.


## Legacy email lookup compatibility
Customer lookup first checks `emailDirectory`. If the receiver account was created before that collection was introduced, the web client falls back to an exact email query against `users`. The included development Firestore rules allow authenticated reads of basic user profiles for this MVP fallback. Tighten/profile-split these rules before production if additional private fields are added to `users`.

## Live transcription (self-hosted)

FiniSpeak now transcribes each participant independently: Customer 1, Customer 2, and the Translator. Each browser sends a copy of only its own microphone as PCM16 to `/ws/transcription`. The WebRTC call remains independent, so a transcription failure does not interrupt the call.

The Flask server uses `faster-whisper`. Raw microphone chunks are held only in memory long enough to transcribe and are not saved. Final text segments are written by the authenticated browser to `calls/{callId}/transcripts/{segmentId}` and all three participants subscribe to that collection for the live transcript panel.

Install the new dependencies with:

```bash
pip install -r requirements.txt
```

The WebSocket verifies Firebase ID tokens and call membership. For local development it can use the existing Firebase web API key plus the signed-in user token, so a service-account file is not required just to test transcription. If `FIREBASE_CREDENTIALS` is configured, Firebase Admin is used instead. Optional transcription settings:

```env
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
TRANSCRIPTION_CHUNK_SECONDS=5.0
```

For a GPU deployment, use a supported CUDA environment and set `WHISPER_DEVICE=cuda` with an appropriate compute type. The first transcription can take longer because the Whisper model may need to be downloaded and loaded.

## Dashboard, incoming calls, and transcript history

Authenticated users are now routed to their dashboard. Customers receive a live Firestore-backed incoming-call popup with Accept/Decline instead of manually entering a Call ID. Translators receive interpretation-request popups and can join the existing three-person call. The dashboard also loads previous calls for the signed-in participant and opens saved `calls/{callId}/transcripts` in a transcript viewer.

The existing development Firestore rules permit these call queries. Before production, tighten call reads/updates and translator request visibility/state transitions.
