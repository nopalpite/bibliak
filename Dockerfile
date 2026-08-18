FROM python:3.12-slim

WORKDIR /app

# System dependencies: build for Pillow, openssl for the self-signed HTTPS
# certificate (needed to unlock camera access on smartphone).
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

# Generates a self-signed HTTPS certificate if needed, creates the tables on
# first launch, then starts the application server over HTTPS.
CMD ["./entrypoint.sh"]
