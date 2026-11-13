# FiniSpeak for iOS

Native SwiftUI client for the FiniSpeak Flask API. Accounts, interpreter search, friends, messages, and live calls all use the same server as the website. Calls join `/ws/signaling` and negotiate audio and video with the same offer, answer, and ICE messages as `views/static/js/webrtc-mesh.js`.

## Run it

1. Start the web backend on your Mac:

```bash
python app.py
```

The development server listens on port 8080.

2. Open `ios/FiniSpeak.xcodeproj` in Xcode. The first open downloads the WebRTC package. That binary is large.
3. Choose an iPhone simulator or a paired iPhone and run the FiniSpeak scheme.
4. The app starts pointed at `http://127.0.0.1:8080`, which reaches a server on the same Mac from the iOS Simulator. On a physical iPhone, open Server and enter the Mac's address, for example `http://192.168.1.20:8080`. The phone and the Mac need to be on the same network.
5. Create an account in the app. A local SQLite backend skips email verification, so you can sign in immediately.

The app allows plain HTTP so it can reach that development server. Point Server at the HTTPS address when you use a deployed backend.

## What the phone can do

- Sign in, create a customer or interpreter account, and reset a password through the existing email flow.
- Search verified interpreters and call one directly.
- Call another customer by email or phone, accept or decline an incoming call, and invite a verified interpreter into a call.
- Hear and see the other people on the call. The microphone is on when you join. Camera stays off until you turn it on. The simulator can place an audio call; camera capture needs an iPhone.
- Read the shared transcript and add a line after you allow transcript saving. Audio is not stored. Saved text uses the same 90-day call transcript as the website.
- Keep friends, direct messages, and the profile phone number in sync with the website. Interpreter availability can be toggled here. Credential uploads stay on the website.
