FROM python:3.12-slim

WORKDIR /app

# Dépendances système : build pour Pillow, openssl pour le certificat HTTPS
# auto-signé (nécessaire pour débloquer l'accès caméra sur smartphone).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    openssl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p instance app/static/covers certs && chmod +x entrypoint.sh

EXPOSE 8000

ENV FLASK_APP=run.py \
    PYTHONUNBUFFERED=1

# Génère un certificat HTTPS auto-signé si nécessaire, crée les tables au
# premier lancement, puis démarre le serveur applicatif en HTTPS.
CMD ["./entrypoint.sh"]
