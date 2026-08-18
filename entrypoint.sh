#!/bin/sh
set -e

# HTTPS_AUTOSIGNE=true (défaut) : le conteneur génère et sert lui-même son
# certificat auto-signé (usage direct, sans reverse proxy devant).
# HTTPS_AUTOSIGNE=false : TLS est supposé terminé en amont (reverse proxy),
# gunicorn sert alors l'app en HTTP simple sur le même port.
HTTPS_AUTOSIGNE="${HTTPS_AUTOSIGNE:-true}"

flask init-db

if [ "$HTTPS_AUTOSIGNE" = "false" ]; then
    echo "HTTPS_AUTOSIGNE=false : démarrage en HTTP simple (TLS délégué à un reverse proxy)."
    exec gunicorn \
        --bind 0.0.0.0:8000 \
        --workers 2 \
        run:app
fi

CERT_DIR="/app/certs"
CERT_FILE="$CERT_DIR/cert.pem"
KEY_FILE="$CERT_DIR/key.pem"

mkdir -p "$CERT_DIR"

# La caméra du smartphone (getUserMedia) n'est autorisée par les navigateurs
# que sur un contexte sécurisé (HTTPS ou localhost). Comme l'application est
# accédée depuis le réseau local (ex: http://192.168.x.x:8000), un certificat
# auto-signé est généré ici pour servir l'app en HTTPS et débloquer le scan
# caméra depuis un smartphone. Le certificat est stocké dans un volume : il
# n'est régénéré qu'une seule fois, sauf si HOST_IP change.

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "Génération d'un certificat HTTPS auto-signé (première initialisation)..."

    SAN="DNS:localhost,IP:127.0.0.1"
    if [ -n "$HOST_IP" ]; then
        SAN="$SAN,IP:$HOST_IP"
    fi

    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "$KEY_FILE" -out "$CERT_FILE" \
        -days 3650 \
        -subj "/CN=ma-bibliotheque.local" \
        -addext "subjectAltName=$SAN" 2>/dev/null

    echo "Certificat généré (SAN: $SAN)."
fi

exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --certfile "$CERT_FILE" \
    --keyfile "$KEY_FILE" \
    run:app
