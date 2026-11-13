# FiniSpeak for iOS

Native SwiftUI client for the FiniSpeak Flask API. Accounts, interpreter search, friends, messages, and live calls all use the same server as the website. Calls join `/ws/signaling` and negotiate audio and video with the same offer, answer, and ICE messages as `views/static/js/webrtc-mesh.js`.

## Run it

1. Open `ios/FiniSpeak.xcodeproj` in Xcode. The first open downloads the WebRTC package. That binary is large.
2. Choose an iPhone simulator or a paired iPhone and run the FiniSpeak scheme.
3. The app starts pointed at `https://finispeak.com`. Sign in with an account on that server.
4. Open Server only when you want a different backend. From the Simulator that can be `http://127.0.0.1:8080` while `python app.py` is running on this Mac. A physical iPhone needs the computer's address, for example `http://192.168.1.20:8080`, and both devices need to be on the same network.

The app allows plain HTTP so it can reach a development server. Production traffic uses HTTPS.

## What the phone can do

- Sign in, create a customer or interpreter account, and reset a password through the existing email flow.
- Search verified interpreters and call one directly.
- Call another customer by email or phone, accept or decline an incoming call, and invite a verified interpreter into a call.
- Hear and see the other people on the call. The microphone is on when you join. Camera stays off until you turn it on. The simulator can place an audio call; camera capture needs an iPhone.
- Read the shared transcript and add a line after you allow transcript saving. Audio is not stored. Saved text uses the same 90-day call transcript as the website.
- Keep friends, direct messages, and the profile phone number in sync with the website. Interpreter availability can be toggled here. Credential uploads stay on the website.
