# Raise Hand — live questions for lectures

Web Application Development (KBTU, Fall 2026) · **Midterm project**: a Dockerized web application with a full REST API.

Students scan a QR code on the projector, ask questions from their phones and upvote the ones they also have. The most wanted questions float to the top of the screen; the lecturer marks them answered. I teach Flutter at KBTU, so this is a tool for my own lectures.

The midterm builds on homework 2 (`hw2-compose/`): the same two-container stack, now with a complete REST API (list / get by id / create / update / delete for **lectures** and **questions**), interactive API documentation and a Postman collection that exercises every endpoint.

```text
 Postman / browser / phone      web (Django 5.2 + gunicorn)          db (PostgreSQL 17)
 ───────────────────────  -p 8000:8000  ───────────────────────  db:5432  ──────────────
 REST API  /api/...  ───────────────▶  qa/api.py   (CRUD, ORM)  ─────────▶  qa_lecture
 Swagger   /docs/    ───────────────▶  qa/views.py + openapi.yaml           qa_question
 HTML pages /, /l/<code>/ ──────────▶  qa/views.py + templates              qa_upvote
                                                                             volume: pgdata
```

## Quick start

Requires Docker Desktop (Compose v2). Nothing else is installed on the host.

```bash
cp .env.example .env          # then change POSTGRES_PASSWORD and DJANGO_SECRET_KEY
docker compose up --build
```

| What | URL |
| --- | --- |
| **API documentation (Swagger UI, "Try it out" works)** | <http://localhost:8000/docs/> |
| OpenAPI 3 spec (import into Postman: *Import → paste the URL*) | <http://localhost:8000/openapi.yaml> |
| API root | <http://localhost:8000/api/> |
| Health check (app + database) | <http://localhost:8000/health/> |
| Lectures list + "Start lecture" | <http://localhost:8000/> |
| Audience page (ask, upvote) | <http://localhost:8000/l/KBTU26/> |
| Projector page (QR code, live board, mark answered) | <http://localhost:8000/l/KBTU26/screen/> |

A demo lecture with code `KBTU26` is created by a data migration on the first start, and with `SEED_DEMO=1` (the default in `.env.example`) the container also loads 8 more lectures with 104 questions and ~270 upvotes, so `GET /api/questions/` returns 100+ records right away.

Stop with `Ctrl+C`, remove the containers with `docker compose down` (the data stays, see below).

## REST API

Full reference with request/response examples: **[`docs/API.md`](docs/API.md)**. Machine-readable description: [`backend/openapi.yaml`](backend/openapi.yaml) (served at `/openapi.yaml`, rendered at `/docs/`).

Two resources, both with the five CRUD operations, plus a few actions. `{key}` is the numeric id **or** the 6-character join code (`KBTU26`); `{id}` is numeric. All bodies are JSON.

| Method | Endpoint | Description | Status |
| --- | --- | --- | --- |
| `GET` | `/api/` | API root: version, links to docs and resources | 200 |
| `GET` | `/health/` | App is up **and** can query the database; used by the Docker `HEALTHCHECK` | 200 / 503 |
| `GET` | `/api/lectures/` | **List** lectures (`?q=` title search, `?is_open=true|false`) | 200 |
| `POST` | `/api/lectures/` | **Create** a lecture: `{"title": "...", "is_open": true}` → join code | 201 |
| `GET` | `/api/lectures/{key}/` | **Get by id** (or code) with its questions, most upvoted first | 200 |
| `PUT` | `/api/lectures/{key}/` | **Update** (full): `{"title": "...", "is_open": ...}` | 200 |
| `PATCH` | `/api/lectures/{key}/` | **Update** (partial): any of `title`, `is_open` | 200 |
| `DELETE` | `/api/lectures/{key}/` | **Delete** the lecture and, by cascade, its questions and upvotes | 204 |
| `POST` | `/api/lectures/{key}/toggle/` | Open / close the lecture for new questions | 200 |
| `GET` | `/api/lectures/{key}/questions/` | **List** the questions of one lecture (screen order) | 200 |
| `POST` | `/api/lectures/{key}/questions/` | **Create** a question: `{"text": "...", "author": "optional"}` | 201 / 409 if closed |
| `GET` | `/api/questions/` | **List** all questions (`?lecture=`, `?answered=`, `?q=`, `?limit=`, `?offset=`) | 200 |
| `GET` | `/api/questions/{id}/` | **Get by id** | 200 |
| `PUT` | `/api/questions/{id}/` | **Update** (full): `{"text": "...", "author": "...", "is_answered": false}` | 200 |
| `PATCH` | `/api/questions/{id}/` | **Update** (partial): any of `text`, `author`, `is_answered` | 200 |
| `DELETE` | `/api/questions/{id}/` | **Delete** the question and its upvotes | 204 |
| `POST` | `/api/questions/{id}/upvote/` | Toggle the caller's upvote (voter = cookie, or `{"voter": "..."}`) | 200 |
| `POST` | `/api/questions/{id}/answered/` | Toggle the answered flag | 200 |

Errors are always `{"error": "message"}`: `400` invalid input, `404` unknown id/code, `405` wrong method, `409` lecture closed, `503` database down.

```bash
B=http://localhost:8000
curl -s $B/api/lectures/ | python3 -m json.tool
curl -s -X POST $B/api/lectures/ -H 'Content-Type: application/json' -d '{"title":"Flutter 1 · Lecture 09"}'
curl -s $B/api/lectures/1/                       # same lecture as  $B/api/lectures/KBTU26/
curl -s -X PATCH $B/api/lectures/1/ -H 'Content-Type: application/json' -d '{"is_open":false}'
curl -s -X POST $B/api/lectures/KBTU26/questions/ -H 'Content-Type: application/json' -d '{"text":"Does EXPOSE publish the port?","author":"Yevgeniy"}'
curl -s "$B/api/questions/?lecture=KBTU26&limit=5"
curl -s -X PUT $B/api/questions/1/ -H 'Content-Type: application/json' -d '{"text":"Edited","author":"Me","is_answered":true}'
curl -i -s -X DELETE $B/api/questions/1/         # HTTP/1.1 204 No Content
```

## Postman collection

[`postman/RaiseHand.postman_collection.json`](postman/RaiseHand.postman_collection.json) (Collection v2.1) contains **30 requests with 59 assertions** covering every endpoint, plus [`postman/local.postman_environment.json`](postman/local.postman_environment.json) with `baseUrl = http://localhost:8000`.

Import both into Postman (*File → Import*), select the "Raise Hand — local" environment and either click through the folders or run the whole thing with the Collection Runner. The folders are ordered as a story: **1** creates a lecture and stores its `lecture_id` / `lecture_code` in collection variables → reads it by id and by code → `PUT` → `PATCH` (closes it) → shows the `409` → reopens it; **2** creates a question in it → lists → `GET` by id → `PUT` → `PATCH` → upvote twice (toggle) → answered → `DELETE` → `404`; **3** deletes the lecture; **4** demonstrates the validation errors (`400`, `404`, `405`). Afterwards the database is exactly as before, so the collection can be run again and again.

From the command line, the same run with [newman](https://www.npmjs.com/package/newman):

```bash
npx newman run postman/RaiseHand.postman_collection.json -e postman/local.postman_environment.json
# → 30 requests, 59 assertions, 0 failed
```

## Services (compose.yaml)

| Service | Image | Role | Ports | Depends on |
| --- | --- | --- | --- | --- |
| `web` | built from `backend/Dockerfile` | Django app served by gunicorn; applies migrations on start | `${WEB_PORT}:8000` | `db` must be **healthy** (`pg_isready`) |
| `db` | `postgres:17-alpine` | PostgreSQL with the named volume `pgdata` | `127.0.0.1:${DB_PORT_HOST}:5432` (host access only, optional) | — |
| `tunnel` (profile `tunnel`, optional) | `cloudflare/cloudflared:2026.10.0` | Public HTTPS address for the classroom demo | — | `web` |

Both services share the `backend` network, so the app reaches the database as `db:5432` — the service name is the hostname. The `tunnel` service only starts with `docker compose --profile tunnel up -d`; the QR code then automatically shows the public address (see "Classroom demo" below).

## Configuration (`.env`)

`.env` is git-ignored and excluded from the image; `.env.example` is the committed template without real credentials (the working `.env` is submitted separately as a zip). Compose reads `.env` twice: `${VAR}` interpolation inside `compose.yaml` (the `db` service) and `env_file:` for the `web` container.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | db, web | Database name, role and password. The postgres image creates them on the first start; Django connects with the same values |
| `DJANGO_SECRET_KEY` | web | Django secret key (required, no default in code) |
| `DJANGO_DEBUG` | web | `1` enables debug mode (default off) |
| `DJANGO_ALLOWED_HOSTS` | web | Comma-separated hosts; add your LAN IP for a demo |
| `APP_NAME` | web | Name in the page header and API root |
| `PUBLIC_URL` | web | Address other devices use; goes into the QR code. Empty = the tunnel address when the `tunnel` service runs, otherwise the address of the current request |
| `TUNNEL_METRICS_URL` | web | Where to ask cloudflared for its hostname (default `http://tunnel:2000`, set in code) |
| `REFRESH_SECONDS` | web | Polling interval of the pages |
| `SEED_DEMO` | web | `1` loads the demo data set on start (idempotent), `0` skips it |
| `WEB_PORT` | compose | Host port for the web service (default 8000) |
| `DB_PORT_HOST` | compose | Host port for PostgreSQL on localhost (default 5433) |

`DB_HOST=db` and `DB_PORT=5432` are set in `compose.yaml` itself because they describe the Compose network, not a secret.

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

Or from DataGrip / psql on the host: `localhost:5433`, database/user from `.env`.

## Useful commands

```bash
docker compose ps                                   # state and health of both services
docker compose logs -f web                          # migrations, then gunicorn access log
docker compose run --rm web python manage.py test   # 35 tests against a temporary PostgreSQL database
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

## Classroom demo (QR code from other devices)

**Option A — phones on the same Wi-Fi.** Put the laptop's LAN address into `.env` and restart the web service:

```bash
ipconfig getifaddr en0                         # macOS: your LAN IP, e.g. 192.168.1.5
# in .env:
#   PUBLIC_URL=http://192.168.1.5:8000           -> encoded into the QR code
#   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.5
docker compose up -d
```

**Option B — phones on any network (tunnel).** The optional `tunnel` service (Cloudflare quick tunnel, no account needed) publishes the app on a temporary public HTTPS address:

```bash
# in .env: PUBLIC_URL=            (empty — otherwise it overrides everything)
docker compose --profile tunnel up -d
```

Open the screen page as usual and the QR code already shows the tunnel address, marked "via Cloudflare tunnel". The backend discovers it itself — cloudflared publishes the random hostname on its metrics endpoint (`GET http://tunnel:2000/quicktunnel`), and `qa/tunnel.py` reads it over the Compose network (cached for a minute). `docker compose --profile tunnel down` stops everything. The address in the terminal: `docker compose logs tunnel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com'`.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `failed to resolve host 'db'` | The web container is not on the Compose network, so the service name `db` does not exist for it. Happens with `docker run raisehand-midterm-web` or when the stack was started half-way. | Start everything together: `docker compose down && docker compose up --build`. Check with `docker network inspect raisehand-midterm_backend` that both containers are listed. |
| `connection refused` for a few attempts, then `Database is up.` | PostgreSQL was still starting. | Nothing: `wait_for_db` retries. |
| `password authentication failed` | `POSTGRES_PASSWORD` in `.env` changed after the volume was created; the role keeps the old password. | Put the old password back, or recreate the volume: `docker compose down -v && docker compose up` (deletes the data). |
| `port is already allocated` | Host port 8000 or 5433 is busy. | Change `WEB_PORT` / `DB_PORT_HOST` in `.env`. |
| `env file .env not found` | `.env` is missing. | `cp .env.example .env` and edit the secrets. |
| `/docs/` shows "Swagger UI could not be loaded" | The viewer script comes from a CDN and the machine is offline. | The spec itself is still at `/openapi.yaml`; `docs/API.md` has the same content. |
| Postman: `Could not get response` | The stack is not running or `baseUrl` points elsewhere. | `docker compose ps`; check the environment's `baseUrl`. |

## How the requirements are covered

| Requirement | Where |
| --- | --- |
| REST API: list, get by id, create, update, delete | `backend/qa/api.py` — lectures and questions (`GET`/`POST`/`PUT`/`PATCH`/`DELETE`), table above |
| Custom Dockerfile for the backend | `backend/Dockerfile` (+ `entrypoint.sh`: wait for the database, migrate, seed) |
| At least one database | `db` service, PostgreSQL 17; Django ORM reads and writes it |
| Docker Compose for all services | `compose.yaml` (`web`, `db`, optional `tunnel`) |
| Networking between containers | `networks: backend`; the app connects to `db:5432` by service name |
| Named volume for persistence | `volumes: pgdata:` mounted at `/var/lib/postgresql/data` |
| Environment variables for configuration | `.env` → `env_file:` and `${VAR}` in `compose.yaml`; `config/settings.py` reads them, secrets have no defaults |
| Starts with `docker compose up` | yes, `--build` on the first run |
| API documentation describing all endpoints | `docs/API.md`, `backend/openapi.yaml`, Swagger UI at `/docs/` |
| Postman collection with working requests for all endpoints | `postman/RaiseHand.postman_collection.json` (+ environment), verified with newman |
| `.env` not committed, placeholders in `.env.example` | `.gitignore`, `.dockerignore`; the working `.env` is in the submitted zip |

## Project structure

```text
midterm/
├── compose.yaml            # services (web, db, optional tunnel), network, volume
├── .env.example            # configuration template (copy to .env)
├── .gitignore
├── README.md
├── docs/
│   └── API.md              # endpoint reference with examples
├── postman/
│   ├── RaiseHand.postman_collection.json   # 30 requests, assertions, chained variables
│   └── local.postman_environment.json      # baseUrl for docker compose
└── backend/
    ├── Dockerfile
    ├── entrypoint.sh       # wait_for_db, migrate, seed_demo (optional), then exec CMD
    ├── .dockerignore
    ├── requirements.txt    # Django, gunicorn, psycopg[binary], segno (QR codes)
    ├── openapi.yaml        # OpenAPI 3 description, served at /openapi.yaml
    ├── manage.py
    ├── config/             # settings read environment variables; urls; wsgi
    └── qa/
        ├── models.py       # Lecture → Question → Upvote
        ├── api.py          # REST endpoints: CRUD for lectures and questions, actions
        ├── views.py        # HTML pages, QR code, /docs/ (Swagger UI), /openapi.yaml
        ├── voters.py       # anonymous voter cookie
        ├── tunnel.py       # finds the public address of the optional tunnel
        ├── management/commands/   # wait_for_db.py, seed_demo.py
        ├── migrations/     # 0001 schema, 0002 demo lecture
        ├── templates/qa/   # base, home, lecture (audience), screen (projector), docs
        └── tests.py        # 35 tests: CRUD, validation, docs, seed, tunnel, pages
```
