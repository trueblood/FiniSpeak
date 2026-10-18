# Self-hosted TURN for FiniSpeak

FiniSpeak can run calls without a metered video provider. The browser clients
remain a small WebRTC mesh and use a self-hosted coturn relay whenever a direct
connection is unavailable. Coturn is open source; traffic uses the existing
server's compute and bandwidth.

TURN is required for dependable phone, cellular, corporate, and carrier-grade
NAT connections. STUN alone is only a development fallback. The JPEG camera
WebSocket is a last-resort picture fallback and does not replace TURN audio and
video transport.

## Network requirements

Give the relay a public hostname, such as `turn.finispeak.com`, and point it at
the relay server. Permit these inbound ports in both the DigitalOcean cloud
firewall and the host firewall:

- UDP and TCP 3478 for TURN/STUN.
- TCP 5349 for TURN over TLS after its certificate is installed.
- UDP and TCP 49160-49200 for relayed media.

Do not expose MySQL or the Flask/Gunicorn application port.

## Coturn configuration

Install the operating system's `coturn` package and configure it with values
equivalent to the following. Replace the example realm, public/private IPs,
certificate paths, and secret before starting the service.

```ini
fingerprint
realm=turn.finispeak.com
use-auth-secret
static-auth-secret=REPLACE_WITH_AT_LEAST_32_RANDOM_BYTES
listening-port=3478
tls-listening-port=5349
min-port=49160
max-port=49200
external-ip=PUBLIC_IP/PRIVATE_IP
cert=/etc/letsencrypt/live/turn.finispeak.com/fullchain.pem
pkey=/etc/letsencrypt/live/turn.finispeak.com/privkey.pem
no-cli
no-multicast-peers
no-loopback-peers
stale-nonce=600
```

Use the same shared secret in `/etc/finispeak/finispeak.env`:

```env
FINISPEAK_STUN_URLS=stun:turn.finispeak.com:3478
FINISPEAK_TURN_URLS=turn:turn.finispeak.com:3478?transport=udp,turn:turn.finispeak.com:3478?transport=tcp
FINISPEAK_TURN_SECRET=THE_SAME_RANDOM_SECRET
```

The deployment workflow runs `scripts/configure_coturn.sh` on every release.
It installs coturn if needed, preserves the existing random secret, updates the
FiniSpeak environment without printing the secret, opens the scoped UFW rules
when UFW is active, and verifies TCP 3478 from the GitHub runner. Set the
optional GitHub repository variable `TURN_HOST` if the relay hostname is not
`finispeak.com`.

TURN over TLS on port 5349 can be added after the relay hostname has a
certificate readable by coturn. UDP and TCP 3478 provide the initial production
relay without a paid service.

Restart coturn and FiniSpeak after updating the environment. The authenticated
`/api/webrtc-config` route issues one-hour pseudonymous TURN credentials; the
shared secret is never returned to a browser.

## Acceptance test

Test with at least two real accounts on different networks, for example a
laptop on Wi-Fi and a phone on cellular data. In the development roster, a
blocked direct connection should change from `turn ready` to `turn relay`, and
both sides must show live audio and video. Then add the translator as a third
participant and verify that all three camera feeds remain visible. Turning one
camera off must replace only that person's feed with the camera-off slate.

Do not declare the deployment ready until `/api/ready` reports
`webrtcRelayConfiguration: true` and the cross-network three-person test passes.
