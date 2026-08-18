#!/bin/sh
set -e

# HTTPS_AUTOSIGNE=true (default): the container generates and serves its own
# self-signed certificate (direct usage, no reverse proxy in front).
# HTTPS_AUTOSIGNE=false: TLS is assumed to be terminated upstream (reverse
# proxy), gunicorn then serves the app in plain HTTP on the same port.
HTTPS_AUTOSIGNE="${HTTPS_AUTOSIGNE:-true}"

flask init-db

if [ "$HTTPS_AUTOSIGNE" = "false" ]; then
    echo "HTTPS_AUTOSIGNE=false: starting in plain HTTP (TLS delegated to a reverse proxy)."
    exec gunicorn \
        --bind 0.0.0.0:8000 \
        --workers 2 \
        run:app
fi

CERT_DIR="/app/certs"
CERT_FILE="$CERT_DIR/cert.pem"
KEY_FILE="$CERT_DIR/key.pem"

mkdir -p "$CERT_DIR"

# Smartphone camera access (getUserMedia) is only allowed by browsers on a
# secure context (HTTPS or localhost). Since the app is accessed from the
# local network (e.g. http://192.168.x.x:8000), a self-signed certificate is
# generated here to serve the app over HTTPS and unlock camera scanning from
# a smartphone. The certificate is stored in a volume: it's only
# regenerated once, unless HOST_IP changes.

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "Generating a self-signed HTTPS certificate (first initialization)..."

    SAN="DNS:localhost,IP:127.0.0.1"
    if [ -n "$HOST_IP" ]; then
        SAN="$SAN,IP:$HOST_IP"
    fi

    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "$KEY_FILE" -out "$CERT_FILE" \
        -days 3650 \
        -subj "/CN=bibliak.local" \
        -addext "subjectAltName=$SAN" 2>/dev/null

    echo "Certificate generated (SAN: $SAN)."
fi

exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --certfile "$CERT_FILE" \
    --keyfile "$KEY_FILE" \
    run:app
