#!/usr/bin/env bash
set -euo pipefail

turn_host="${1:?TURN hostname is required}"
app_env="${2:-/etc/finispeak/finispeak.env}"
external_address="${3:-$turn_host}"
secret_file="/etc/finispeak/turn.secret"
turn_config="/etc/turnserver.conf"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "configure_coturn.sh must run as root" >&2
    exit 1
fi

if [[ ! "$turn_host" =~ ^[A-Za-z0-9.-]+$ ]]; then
    echo "Invalid TURN hostname" >&2
    exit 1
fi

external_ip="$(getent ahostsv4 "$external_address" | awk 'NR == 1 { print $1 }')"
if [[ -z "$external_ip" ]]; then
    echo "Could not resolve the droplet's public IPv4 address" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq coturn

install -d -m 0750 /etc/finispeak
if [[ ! -s "$secret_file" ]]; then
    umask 077
    openssl rand -hex 32 > "$secret_file"
fi
turn_secret="$(tr -d '\r\n' < "$secret_file")"
if [[ ${#turn_secret} -lt 32 ]]; then
    echo "The persisted TURN secret is invalid" >&2
    exit 1
fi

install -o root -g turnserver -m 0640 /dev/null "$turn_config"
printf '%s\n' \
    "fingerprint" \
    "realm=$turn_host" \
    "server-name=$turn_host" \
    "use-auth-secret" \
    "static-auth-secret=$turn_secret" \
    "listening-port=3478" \
    "external-ip=$external_ip" \
    "min-port=49160" \
    "max-port=49200" \
    "stale-nonce=600" \
    "total-quota=200" \
    "no-cli" \
    "no-multicast-peers" \
    "no-loopback-peers" \
    "no-tls" \
    "no-dtls" > "$turn_config"

if [[ -f /etc/default/coturn ]]; then
    if grep -q '^TURNSERVER_ENABLED=' /etc/default/coturn; then
        sed -i 's/^TURNSERVER_ENABLED=.*/TURNSERVER_ENABLED=1/' /etc/default/coturn
    else
        printf '%s\n' 'TURNSERVER_ENABLED=1' >> /etc/default/coturn
    fi
fi

upsert_env() {
    local key="$1"
    local value="$2"
    local temporary
    temporary="$(mktemp)"
    if [[ -f "$app_env" ]]; then
        grep -v "^${key}=" "$app_env" > "$temporary" || true
        chown --reference="$app_env" "$temporary"
        chmod --reference="$app_env" "$temporary"
    else
        install -o root -g root -m 0600 /dev/null "$app_env"
    fi
    printf '%s=%s\n' "$key" "$value" >> "$temporary"
    mv "$temporary" "$app_env"
}

upsert_env "FINISPEAK_STUN_URLS" "stun:${turn_host}:3478"
upsert_env "FINISPEAK_TURN_URLS" "turn:${turn_host}:3478?transport=udp,turn:${turn_host}:3478?transport=tcp"
upsert_env "FINISPEAK_TURN_SECRET" "$turn_secret"

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q '^Status: active'; then
    ufw allow 3478/udp comment 'FiniSpeak TURN' >/dev/null
    ufw allow 3478/tcp comment 'FiniSpeak TURN' >/dev/null
    ufw allow 49160:49200/udp comment 'FiniSpeak TURN media' >/dev/null
    ufw allow 49160:49200/tcp comment 'FiniSpeak TURN media' >/dev/null
fi

systemctl enable coturn >/dev/null
systemctl restart coturn
systemctl is-active --quiet coturn
ss -lntu | grep -Eq '[:.]3478[[:space:]]'

echo "coturn is configured and listening on ${turn_host}:3478"
