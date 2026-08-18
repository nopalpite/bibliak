# BIBLIAK

Local app for managing a comic book and book collection — no account, no authentication, built for personal single-user use.

Built to the agreed spec: Flask + SQLite, HTMX + Alpine.js for dynamic interactions, TailwindCSS for styling, all packaged with Docker.

## Features

- Collection browsable as a grid (covers), a list (table), or **shelves** (grouped by series, sorted by volume — with a dedicated page per series showing missing volumes if the total volume count is set)
- Instant search (title, author, publisher, series, ISBN) + combinable filters (type, series, publisher, tag, location, condition) + sorting
- Manual book entry with tags, location, authors, autocomplete on existing reference data. Series and publisher must be chosen from existing entries (dropdown, with quick creation via a "+" button without leaving the page) to avoid duplicates caused by typos. The volume number is set via an incremental stepper (+/-) as well as direct input.
- Add by barcode scan (smartphone camera) or manual ISBN entry (desktop/tablet), with automatic metadata retrieval via Open Library (falling back to Google Books)
- Automatic cover retrieval, or manual photo capture / upload
- Single-page administration (tabs, no page reload): general settings, reference data management (types, conditions, publishers, series, tags, locations — with duplicate merging), JSON export/import of the whole collection
- **Duplicate detection**, applied uniformly everywhere (manual add, scan, import): by ISBN first, falling back to title + volume if the ISBN is missing. Live warning while typing, blocked on save with the option to confirm anyway, duplicates automatically skipped on import. Policy is configurable (or can be disabled) from Administration > Settings.
- **Read status**: read / unread, toggle button on the detail page, dedicated filter on the Collection page, preserved on JSON export/import
- Dark / light mode, available from first launch

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up -d --build
```

The app is then reachable at `https://localhost:8000` from the PC hosting the container, and at `https://<machine-ip>:8000` from another device on the local network (notably your smartphone).

Data (SQLite database and covers) is kept in `./data/`, outside the container: it survives image updates and rebuilds.

To stop the app:

```bash
docker compose down
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
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── run.py
├── app/
│   ├── config.py            # configuration (paths, API keys...)
│   ├── extensions.py         # SQLAlchemy, Migrate
│   ├── models/                # Book, Author, Publisher, Series, Tag, Location, Setting
│   ├── services/               # business logic (search, isbn, image, book, series, settings)
│   ├── routes/                  # Flask blueprints (main, books, scan, admin)
│   ├── templates/                 # Jinja2 (layout, pages, HTMX fragments, admin)
│   └── static/                      # JS (htmx/alpine/scanner) and stored covers
└── data/                     # created on first Docker launch (database + covers), not versioned
```

## Adding a new feature

The architecture is deliberately layered to stay easy to evolve:

1. **Model** (`app/models/`) if new data needs to be stored.
2. **Service** (`app/services/`) for business logic — never put logic in routes.
3. **Route** (`app/routes/`) to expose the feature, in the relevant blueprint (or a new blueprint if the domain is distinct).
4. **Template** (`app/templates/`) for display; reuse the existing HTMX fragments as a model for any new dynamic view.

## Schema evolution (migrations)

The very first launch creates the tables directly (`flask init-db`, already wired into the Docker image). If you later modify the models and want schema version tracking via Alembic:

```bash
docker compose exec biblio-app flask db init
docker compose exec biblio-app flask db migrate -m "change description"
docker compose exec biblio-app flask db upgrade
```

## ISBN metadata sources

- [Open Library Books API](https://openlibrary.org/dev/docs/api/books) — free, no key required
- [Google Books API](https://developers.google.com/books) — free, optional key (`GOOGLE_BOOKS_API_KEY` in `.env`) for higher quotas

The priority source is configured from the Administration > Settings page.

Each call sends a `User-Agent` header identifying the app. Open Library recommends including a contact (email or phone) in it: in exchange, the rate limit goes from 1 to 3 requests per second, and they can warn you in case of abnormal volume instead of silently blocking you. Set `CONTACT_INFO` in `.env` to benefit from this (optional, but recommended if you scan a lot of books in a row).
