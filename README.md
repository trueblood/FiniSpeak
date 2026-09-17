# FiniSpeak

FiniSpeak is an on-demand human translation platform. The first client is a Flask web app, with the backend and call model designed to be reused by future native iOS and Android apps.

## Initial architecture

- Flask web/API
- Firebase Authentication (client integration next)
- Cloud Firestore
- WebRTC calling (next milestone)
- Three-person call model: Customer 1 calls Customer 2, then a translator can join the active session

Firebase Storage and Firebase Cloud Messaging are intentionally deferred until later.

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Download your Firebase Admin SDK service-account JSON file, save it as `firebase-service-account.json` in the project root, and keep it out of Git.

Then run:

```bash
python app.py
```

Open `http://127.0.0.1:5050`.

The homepage runs without Firebase credentials. Firestore-backed API endpoints will return a configuration error until `FIREBASE_CREDENTIALS` is configured.

## API foundation

- `GET /api/users/`
- `GET /api/translators/`
- `POST /api/calls/`

Example call creation body:

```json
{
  "callerId": "customer_1",
  "receiverId": "customer_2"
}
```

The translator is intentionally not required when the call is created. A translator will be requested and added to the existing customer-to-customer session in the next phase.
