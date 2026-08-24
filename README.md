# BIBLIAK

Self-hosted app for managing a comic book and book collection — no account, no authentication, single-user. Flask + SQLite, HTMX + Alpine.js, TailwindCSS, packaged with Docker.

## Features

- Collection browsable as a grid (covers), a list (table), or **shelves** (grouped by series, sorted by volume — with a dedicated page per series showing missing volumes if the total volume count is set)
- Instant search (title, author, publisher, series, ISBN) + combinable filters (type, series, publisher, tag, location, condition) + sorting
- Manual book entry with tags, location, authors, autocomplete on existing reference data. Series and publisher must be chosen from existing entries (dropdown, with quick creation via a "+" button without leaving the page) to avoid duplicates caused by typos. The volume number is set via an incremental stepper (+/-) as well as direct input.
- Add by barcode scan (smartphone camera) or manual ISBN entry (desktop/tablet), with automatic metadata retrieval via Open Library
- Automatic cover retrieval, or manual photo capture / upload
- Single-page administration (tabs, no page reload): general settings, reference data management (types, conditions, publishers, series, tags, locations — with duplicate merging), JSON and CSV export/import of the whole collection
- **Duplicate detection**, applied uniformly everywhere (manual add, scan, import): by ISBN first, falling back to title + volume if the ISBN is missing. Live warning while typing, blocked on save with the option to confirm anyway, duplicates automatically skipped on import. Policy is configurable (or can be disabled) from Administration > Settings.
- **Read status**: read / unread, toggle button on the detail page, dedicated filter on the Collection page, preserved on export/import
- **Bulk actions** on the Collection page (grid and list views): select multiple books to add a tag, set a location, or delete them in one go
- **Stats page**: totals, read/unread split, breakdown by type, publisher, author, and decade
- Dark / light mode, available from first launch

## Quick start (Docker)

**Prerequisites**: [Docker](https://docs.docker.com/get-docker/) and Docker Compose (bundled with Docker Desktop, or the `docker-compose-plugin` package on Linux).

1. Clone the repository and move into it:

   ```bash
   git clone https://github.com/nopalpite/bibliak.git
   cd bibliak
   ```

2. Create your `.env` file from the example, and adjust it if needed (see [Environment variables](#environment-variables) below — the defaults work out of the box for a first try):

   ```bash
   cp .env.example .env
   ```

3. Build the image and start the container:

   ```bash
   docker compose up -d --build
   ```

   This builds the image locally from the `Dockerfile` (nothing is pulled from a registry). First build takes a minute or two; subsequent ones are cached.

4. Open the app:
   - From the PC hosting the container: `https://localhost:8000`
   - From another device on the local network (e.g. your smartphone): `https://<machine-ip>:8000` — see [Enabling camera scanning from a smartphone](#enabling-camera-scanning-from-a-smartphone) to make the certificate valid for that address.

**Data persistence**: the SQLite database, the cover images, and the self-signed certificate are kept in `./data/` on the host, outside the container — they survive `docker compose down`, image rebuilds, and updates.

**Useful commands**:

```bash
docker compose logs -f          # follow the app's logs
docker compose restart          # restart after editing .env
docker compose up -d --build    # rebuild and restart after pulling code changes
docker compose down             # stop and remove the container (data in ./data/ is kept)
```

### Enabling camera scanning from a smartphone

Browsers (Chrome, Safari...) only allow camera access over an **HTTPS** connection (or `localhost`). Since the app is accessed from the local network over `http://` by default, camera scanning would be silently blocked by the phone. To avoid this, the container automatically generates a **self-signed HTTPS certificate** on first launch and serves the app over HTTPS.

For this certificate to be valid for your machine's IP address (not just `localhost`):

1. Find the local IP address of the machine hosting Docker (e.g. `192.168.1.20`) — `ip a` on Linux, `ipconfig` on Windows.
2. Set it in `.env`: `HOST_IP=192.168.1.20`
3. Restart: `docker compose up -d --build`
4. From your smartphone, open `https://192.168.1.20:8000`

Since the certificate is self-signed, the browser will show a security warning ("Connection not private" or similar): this is expected for a self-hosted app without a public domain name. Choose "Advanced" then "Proceed to site" — this warning will only appear once per device. Once the page is accepted, camera access works normally.

The certificate is stored in `./data/certs` and is only regenerated once (unless this folder is manually deleted or `HOST_IP` changes).

If the message *"Camera access unavailable"* still shows up on the Scanner page, check that the URL starts with `https://` and not `http://`.

### Running behind a reverse proxy

If TLS is terminated upstream by a reverse proxy, set `HTTPS_AUTOSIGNE=false` in `.env`: the container stops generating a certificate and serves the app in plain HTTP on port 8000.

### Deploying a pre-built image (Portainer, Dockge, ...)

Every push to `master` publishes a multi-arch image (`linux/amd64` + `linux/arm64`) to `ghcr.io/nopalpite/bibliak`. If you manage containers through a stack UI like [Portainer](https://www.portainer.io/) or [Dockge](https://github.com/louislam/dockge), you can paste this directly as a new stack — no need to clone the repository or build anything:

```yaml
services:
  bibliak:
    image: ghcr.io/nopalpite/bibliak:latest
    container_name: bibliak
    ports:
      - "8000:8000"
    volumes:
      - ./data/instance:/app/instance
      - ./data/covers:/app/app/static/covers
      - ./data/certs:/app/certs
    environment:
      SECRET_KEY: change-me-in-production      # set a real random value
      DATABASE_PATH: instance/biblio.sqlite3
      CONTACT_INFO: ""                          # optional, e.g. you@example.com
      HOST_IP: ""                                # your server's LAN IP, e.g. 192.168.1.20
      HTTPS_AUTOSIGNE: "true"                    # "false" if a reverse proxy handles TLS
    restart: unless-stopped
```

See [Environment variables](#environment-variables) below for what each one does, and [Enabling camera scanning from a smartphone](#enabling-camera-scanning-from-a-smartphone) for `HOST_IP`.

> **Note**: the `bibliak` package on GHCR is currently **private**. Either make it public (repo → Packages → `bibliak` → Package settings), or authenticate your Docker host with a [GitHub personal access token](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-to-the-container-registry) (`read:packages` scope). Otherwise, use the "build from source" method above instead.

## Environment variables

All variables are read from `.env` (copied from `.env.example`). None are required to get started — the defaults are sensible for local, single-user use.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Flask session signing key. Only used for the short-lived scan pre-fill session; low-stakes here, but worth setting to a random value (`python -c "import secrets; print(secrets.token_hex(32))"`) if the app is reachable beyond your own machine. |
| `DATABASE_PATH` | `instance/biblio.sqlite3` | Path to the SQLite database file, relative to the project root. With Docker, this lives inside the container at that path, which is mounted to `./data/instance/` on the host — you shouldn't need to change it. |
| `CONTACT_INFO` | *(empty)* | An email or phone number sent in the `User-Agent` header to Open Library. Recommended: Open Library grants a 3x higher rate limit (3 req/s instead of 1) to identified requests. |
| `HOST_IP` | *(empty)* | Local IP address of the machine hosting Docker (e.g. `192.168.1.20`). Needed so the self-signed HTTPS certificate is valid for that address too, not just `localhost` — required for camera scanning from a smartphone on the network. |
| `HTTPS_AUTOSIGNE` | `true` | `true`: the container generates and serves its own self-signed HTTPS certificate. `false`: TLS is assumed to be terminated upstream (reverse proxy); the container serves plain HTTP on port 8000. See [Running behind a reverse proxy](#running-behind-a-reverse-proxy) above. |

## Local development (without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask init-db
flask run --debug --port 8000
```

## Project layout

```
biblio-app/
├── .github/workflows/   # CI (lint + tests) and Docker image publish
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt # + pytest, ruff
├── run.py
├── app/
│   ├── config.py        # configuration (paths, CONTACT_INFO...)
│   ├── extensions.py    # SQLAlchemy, Migrate
│   ├── translations/    # UI strings, one flat JSON file per language
│   ├── models/          # Book, Author, Publisher, Series, Tag, Location, Setting
│   ├── services/        # business logic (search, isbn, image, book, settings, i18n)
│   ├── routes/          # Flask blueprints (main, books, scan, admin)
│   ├── templates/       # Jinja2 (layout, pages, HTMX fragments, admin)
│   └── static/          # JS (htmx/alpine/scanner) and stored covers
├── tests/                # pytest suite (services + routes)
└── data/                 # created on first Docker launch (database + covers), not versioned
```

## Adding a new feature

The architecture is deliberately layered to stay easy to evolve:

1. **Model** (`app/models/`) if new data needs to be stored.
2. **Service** (`app/services/`) for business logic — never put logic in routes.
3. **Route** (`app/routes/`) to expose the feature, in the relevant blueprint (or a new blueprint if the domain is distinct).
4. **Template** (`app/templates/`) for display; reuse the existing HTMX fragments as a model for any new dynamic view.

## Schema evolution (migrations)

Schema changes are tracked with Alembic (`migrations/`), applied via `flask init-db` on every container start (already wired into the Docker image and `entrypoint.sh`). An install that predates this (tables already exist, no `alembic_version` table yet) is detected automatically and stamped as already matching the baseline migration instead of Alembic trying to re-create tables that are already there.

After changing a model, generate and commit the migration:

```bash
docker compose exec biblio-app flask db migrate -m "change description"
docker compose exec biblio-app flask db upgrade
```

## ISBN metadata source

Metadata (title, authors, publisher, cover...) is retrieved from the [Open Library Books API](https://openlibrary.org/dev/docs/api/books) — free, no key required. See `CONTACT_INFO` above for a higher rate limit.
