# Raise Hand — live questions for lectures

Web Application Development (KBTU, Fall 2026) · Homework #2: multi-container application with Docker Compose.

Students scan a QR code on the projector, ask questions from their phones and upvote the ones they also have. The most wanted questions float to the top of the screen; the lecturer marks them answered. I teach Flutter at KBTU, so this is a tool for my own lectures.

Two containers, started with one command:

```text
 phone / laptop                 web (Django + gunicorn)              db (PostgreSQL 17)
 ───────────────  -p 8000:8000  ──────────────────────  db:5432  ────────────────────
 HTML pages ─────────────────▶  qa/views.py                        qa_lecture
 JSON API  ─────────────────▶  qa/api.py  ──────────────────────▶  qa_question
                                 reads AND writes via Django ORM     qa_upvote
                                                                     volume: pgdata
```

## Quick start

Requires Docker Desktop (Compose v2). Nothing else is installed on the host.

```bash
cp .env.example .env          # then change POSTGRES_PASSWORD and DJANGO_SECRET_KEY
docker compose up --build
```

Open <http://localhost:8000>. A demo lecture with code `KBTU26` is created by a data migration on the first start, and with `SEED_DEMO=1` (the default in `.env.example`) the container also loads 8 more lectures with 104 questions and ~270 upvotes, so there is plenty to click right away:

| Page | URL |
| --- | --- |
| Lectures list + "Start lecture" | <http://localhost:8000/> |
| Audience page (ask, upvote) | <http://localhost:8000/l/KBTU26/> |
| Projector page (QR code, live board, mark answered) | <http://localhost:8000/l/KBTU26/screen/> |

Stop with `Ctrl+C`, remove the containers with `docker compose down` (the data stays, see below).

### Classroom demo, option A: phones on the same Wi-Fi

Phones must reach your laptop, so put its LAN address into `.env` and restart the web service:

```bash
ipconfig getifaddr en0                         # macOS: your LAN IP, e.g. 192.168.1.5
# in .env:
#   PUBLIC_URL=http://192.168.1.5:8000           -> encoded into the QR code
#   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.5
docker compose up -d
```

Many campus networks isolate clients from each other; if a phone cannot open the address, use option B or share your phone's hotspot with the laptop.

### Classroom demo, option B: phones on any network (tunnel)

The optional `tunnel` service (Cloudflare quick tunnel, no account needed) publishes the app on a temporary public HTTPS address, so the audience can use mobile data:

```bash
# in .env: PUBLIC_URL=            (empty — otherwise it overrides everything)
docker compose --profile tunnel up -d
```

That is all: open the screen page as usual (`http://localhost:8000/l/KBTU26/screen/`) and the QR code already shows the tunnel address, marked "via Cloudflare tunnel". The backend discovers it itself — cloudflared publishes the random hostname on its metrics endpoint (`GET http://tunnel:2000/quicktunnel`), and `qa/tunnel.py` reads it over the Compose network (cached for a minute). The address changes on every start of the tunnel, which is why it is not written into `.env`. `docker compose --profile tunnel down` stops everything.

To see the address in the terminal: `docker compose logs tunnel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com'`.

## Services (compose.yaml)

| Service | Image | Role | Ports | Depends on |
| --- | --- | --- | --- | --- |
| `web` | built from `backend/Dockerfile` | Django app served by gunicorn; applies migrations on start | `${WEB_PORT}:8000` | `db` must be **healthy** (`pg_isready`) |
| `db` | `postgres:17-alpine` | PostgreSQL with the named volume `pgdata` | `127.0.0.1:${DB_PORT_HOST}:5432` (host access only, optional) | — |
| `tunnel` (profile `tunnel`, optional) | `cloudflare/cloudflared:2026.10.0` | Public HTTPS address for the classroom demo | — | `web` |

Both services share the `backend` network, so the app reaches the database as `db:5432` — the service name is the hostname.

## Configuration (`.env`)

`.env` is git-ignored and excluded from the image; `.env.example` is the committed template without real credentials. Compose reads `.env` twice: `${VAR}` interpolation inside `compose.yaml` (the `db` service) and `env_file:` for the `web` container.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | db, web | Database name, role and password. The postgres image creates them on the first start; Django connects with the same values |
| `DJANGO_SECRET_KEY` | web | Django secret key |
| `DJANGO_DEBUG` | web | `1` enables debug mode (default off) |
| `DJANGO_ALLOWED_HOSTS` | web | Comma-separated hosts; add your LAN IP for a demo |
| `APP_NAME` | web | Name in the page header |
| `PUBLIC_URL` | web | Address other devices use; goes into the QR code. Empty = the tunnel address when the `tunnel` service runs, otherwise the address of the current request |
| `TUNNEL_METRICS_URL` | web | Where to ask cloudflared for its hostname (default `http://tunnel:2000`, set in code) |
| `REFRESH_SECONDS` | web | Polling interval of the pages |
| `SEED_DEMO` | web | `1` loads the demo data set on start (idempotent), `0` skips it |
| `WEB_PORT` | compose | Host port for the web service (default 8000) |
| `DB_PORT_HOST` | compose | Host port for PostgreSQL on localhost (default 5433) |

`DB_HOST=db` and `DB_PORT=5432` are set in `compose.yaml` itself because they describe the Compose network, not a secret.

## API

All writes go through the JSON API; the HTML pages are shells that call it from JavaScript.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health/` | App is up **and** can query the database (`SELECT version()`); used by the Docker `HEALTHCHECK` |
| `GET` | `/api/lectures/` | All lectures with question counts |
| `POST` | `/api/lectures/` | Create a lecture: `{"title": "..."}` → join code |
| `GET` | `/api/lectures/<code>/` | Lecture with its questions, most upvoted first, answered at the bottom |
| `POST` | `/api/lectures/<code>/questions/` | Ask: `{"text": "...", "author": "optional"}` |
| `POST` | `/api/lectures/<code>/toggle/` | Open / close the lecture for new questions |
| `POST` | `/api/questions/<id>/upvote/` | Toggle the caller's upvote (voter = cookie, or `{"voter": "..."}` in the body) |
| `POST` | `/api/questions/<id>/answered/` | Mark answered / reopen |

```bash
curl -s localhost:8000/health/
curl -s -X POST localhost:8000/api/lectures/ -H 'Content-Type: application/json' -d '{"title":"Flutter 1 · Lecture 04"}'
curl -s -X POST localhost:8000/api/lectures/KBTU26/questions/ -H 'Content-Type: application/json' -d '{"text":"Does EXPOSE publish the port?","author":"Yevgeniy"}'
curl -s -X POST localhost:8000/api/questions/1/upvote/ -H 'Content-Type: application/json' -d '{"voter":"me"}'
curl -s localhost:8000/api/lectures/KBTU26/ | python3 -m json.tool
```

## Demo data

`python manage.py seed_demo` fills the database with a realistic data set: 8 lectures of a Flutter course (Dart basics, widgets, state management, navigation, networking, storage, animations, testing and release), 104 questions with authors and timestamps spread over each lecture slot, 273 upvotes from 40 anonymous voters, and about 40 % of the questions in finished lectures marked as answered. The generator uses a fixed random seed, so every machine gets the same numbers.

```bash
docker compose exec web python manage.py seed_demo            # runs automatically on start when SEED_DEMO=1
docker compose exec web python manage.py seed_demo --clear    # drop the demo lectures and generate them again
```

The demo lectures have fixed join codes (`FLT101`–`FLT108`), which is how the command finds its own data: a second run changes nothing. The home page shows the totals read from the database.

## Data persistence

PostgreSQL stores its files in the named volume `pgdata`, which is independent of the container:

```bash
docker compose down        # containers and network removed, volume kept
docker compose up -d       # same lectures, questions and votes are back
docker compose down -v     # -v removes the volume: this is the only way to lose the data
```

Look at the data directly:

```bash
docker compose exec db psql -U raisehand -d raisehand -c 'SELECT id, code, title FROM qa_lecture;'
docker compose exec db psql -U raisehand -d raisehand -c 'SELECT question_id, count(*) FROM qa_upvote GROUP BY 1;'
docker volume ls | grep pgdata
```

## Useful commands

```bash
docker compose ps                                   # state and health of both services
docker compose logs -f web                          # migrations, then gunicorn access log
docker compose run --rm web python manage.py test   # 22 tests against a temporary PostgreSQL database
docker compose exec web sh                          # shell inside the app container (user: appuser)
docker compose build                                # rebuild the image after a code change
docker compose up -d --build                        # rebuild and recreate in one go
```

## Startup sequence

`docker compose up` starts `db` first and waits for its healthcheck. The `web` container then runs `entrypoint.sh`:

1. `python manage.py wait_for_db` — retries the connection every 2 s (up to 60 s) and prints one line per attempt, e.g. `attempt 1/30: connection refused`;
2. `python manage.py migrate --noinput` — applies migrations (creates the tables and the demo lecture on the first start);
3. `python manage.py seed_demo` — only when `SEED_DEMO=1`; loads the demo data set once;
4. `exec gunicorn …` — the `CMD` from the Dockerfile.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `failed to resolve host 'db'` | The web container is not on the Compose network, so the service name `db` does not exist for it. Happens with `docker run raisehand-web` or when the stack was started half-way. | Start everything together: `docker compose down && docker compose up --build`. Check with `docker network inspect raisehand_backend` that both containers are listed. |
| `connection refused` for a few attempts, then `Database is up.` | PostgreSQL was still starting. | Nothing: `wait_for_db` retries. |
| `password authentication failed` | `POSTGRES_PASSWORD` in `.env` changed after the volume was created; the role keeps the old password. | Put the old password back, or recreate the volume: `docker compose down -v && docker compose up` (deletes the data). |
| `port is already allocated` | Host port 8000 or 5433 is busy. | Change `WEB_PORT` / `DB_PORT_HOST` in `.env`. |
| `env file .env not found` | `.env` is missing. | `cp .env.example .env` and edit the secrets. |

## How the requirements are covered

| Requirement | Where |
| --- | --- |
| Backend with a meaningful API | `backend/qa/api.py`, table above |
| Relational database | `db` service, PostgreSQL 17 |
| Backend reads and writes the database | Django ORM in `qa/api.py`; raw `SELECT version()` in `/health/` |
| `compose.yaml` with backend and database | `compose.yaml` |
| Custom Dockerfile for the backend | `backend/Dockerfile` (+ `entrypoint.sh`: wait for the database, migrate) |
| Ports, networks, service names, dependencies | `ports:`, `networks: backend`, `DB_HOST=db`, `depends_on … service_healthy` |
| Environment variables for DB and app config | `.env` → `env_file:` and `${VAR}` in `compose.yaml`; `config/settings.py` |
| No hardcoded secrets, `.env` not committed | `.gitignore`, `.dockerignore`; `.env.example` has placeholders only |
| Named volume, data survives recreation | `volumes: pgdata:` |
| `.dockerignore` and `.gitignore` | `backend/.dockerignore`, `.gitignore` |
| Starts with `docker compose up` | yes, `--build` on the first run |

## Project structure

```text
hw2-compose/
├── compose.yaml            # services (web, db, optional tunnel), network, volume
├── .env.example            # configuration template (copy to .env)
├── .gitignore
└── backend/
    ├── Dockerfile
    ├── entrypoint.sh       # wait_for_db, migrate, seed_demo (optional), then exec CMD
    ├── .dockerignore
    ├── requirements.txt    # Django, gunicorn, psycopg[binary], segno (QR codes)
    ├── manage.py
    ├── config/             # settings read environment variables; urls; wsgi
    └── qa/
        ├── models.py       # Lecture → Question → Upvote
        ├── api.py          # JSON endpoints (reads and writes)
        ├── views.py        # HTML pages, QR code generation
        ├── voters.py       # anonymous voter cookie
        ├── tunnel.py       # finds the public address of the optional tunnel
        ├── management/commands/   # wait_for_db.py, seed_demo.py
        ├── migrations/     # 0001 schema, 0002 demo lecture
        ├── templates/qa/   # base, home, lecture (audience), screen (projector)
        └── tests.py
```
