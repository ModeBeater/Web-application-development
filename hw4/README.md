# Raise Hand — live questions for lectures

Web Application Development (KBTU, Fall 2026) · **Homework 4 / Endterm · final project: Complete Containerized Web Application**.

Students scan a QR code on the projector, ask questions from their phones and upvote the ones they also have. The most wanted questions float to the top of the screen; the lecturer marks them answered. I teach Flutter at KBTU, so this is a tool for my own lectures.

This is the complete application: the HW3 REST API (Django REST Framework) plus **JWT authentication** (access + refresh tokens with rotation and blacklist), **three roles** (student / lecturer / admin) with permissions on every write, a **personal cabinet**, **user management**, and a **client-side frontend** that talks to the API with the tokens the browser holds — all running from `docker compose up`.

The final version adds what makes the tool useful after the lecture, not only during it:

* **Topic plan** — a lecture has topics (one-to-many); the lecturer types them in or **uploads the lecture text** (.txt / .md / .pdf, one-to-one with the lecture) and the headings become topics with TF-IDF keywords.
* **Automatic tagging** — when a student asks, a small offline model (`qa/tagging.py`: character n-gram TF-IDF + keyword bonus, scikit-learn) files the question under the right topic, or leaves it untagged when unsure; the student can also pick the topic. Every question carries `tag_source` (`auto` / `manual`) and the model's confidence.
* **“Already asked?”** — while typing, similar existing questions are shown with an upvote button, so duplicates become votes.
* **Written answers** — one per question (one-to-one): the lecturer answers in text, the audience sees it under the question, deleting the question deletes the answer.
* **Summary and export** — questions per topic for the lecturer, Markdown export of the whole lecture (topics → questions → answers) to send to the group.

```text
 browser / phone                    web (Django 5.2 + DRF + SimpleJWT + gunicorn)      db (PostgreSQL 17)
 ──────────────────  -p 8000:8000   ───────────────────────────────────────────  db:5432  ──────────────
 pages  /, /login/, /me/, /l/… ──▶  templates + static/qa/app.js (JWT client)            accounts_user
 REST   /api/auth/*  ────────────▶  accounts/api.py   register · login · refresh · me   ─▶ qa_lecture
        /api/lectures|questions ─▶  qa/api.py         viewsets + permissions.py            qa_question
        /api/users/  ────────────▶  accounts/api.py   admin only                            qa_upvote
 docs   /docs/ (Swagger)  ───────▶  drf-spectacular                                         token_blacklist_*
                                                                                             volume: pgdata
```

## Quick start

Requires Docker Desktop (Compose v2). Nothing else is installed on the host.

```bash
cp .env.example .env          # then change POSTGRES_PASSWORD and DJANGO_SECRET_KEY (≥ 32 characters)
docker compose up --build
```

Open <http://localhost:8000> and sign in with a demo account (password `Demo12345!`, set by `DEMO_PASSWORD` in `.env`):

| Account | Role | Try |
| --- | --- | --- |
| `admin` | admin | **Users** page: change roles, deactivate, delete; everything below too |
| `lecturer` | lecturer | **Personal cabinet** → My lectures: start a lecture, open the projector **Screen**, close it, mark questions answered |
| `student` (also `aigerim`, `daniyar`, `student01…student40`) | student | **Join** a lecture from a phone: ask, upvote, edit own questions |

| What | URL |
| --- | --- |
| Lectures (search, filters, start a lecture) | <http://localhost:8000/> |
| Sign in / Create account | <http://localhost:8000/login/> · <http://localhost:8000/register/> |
| Personal cabinet (profile, password, my lectures, my questions, tokens) | <http://localhost:8000/me/> |
| Users (admin) | <http://localhost:8000/users/> |
| Audience page / projector screen of the demo lecture | <http://localhost:8000/l/KBTU26/> · <http://localhost:8000/l/KBTU26/screen/> |
| **API docs (Swagger UI with Authorize)** | <http://localhost:8000/docs/> |
| OpenAPI schema · API root · health | <http://localhost:8000/api/schema/> · <http://localhost:8000/api/> · <http://localhost:8000/health/> |

With `SEED_DEMO=1` (default) the first start also creates 40 student accounts, 8 lectures of a Flutter course, 104 questions and ~330 upvotes, so the lists have 100+ records right away.

## Authentication and authorization

**JWT with `djangorestframework-simplejwt`.** `POST /api/auth/login/` returns an **access token** (15 minutes, sent as `Authorization: Bearer …` with every request; carries `user_id`, `username`, `role`) and a **refresh token** (7 days). When the access token expires the client calls `POST /api/auth/refresh/` and receives a **new pair**: refresh tokens are rotated and the used one is blacklisted (`token_blacklist` app), so a leaked refresh token stops working as soon as the real client refreshes. `POST /api/auth/logout/` blacklists the refresh token explicitly. Registration (`POST /api/auth/register/`) applies Django's password validators and signs the new user in. The profile endpoints (`GET/PATCH /api/auth/me/`, `POST /api/auth/me/password/`) back the personal cabinet.

**Roles** are a column on the custom user model (`accounts.User.role`): `student`, `lecturer`, `admin`. **Permissions** are DRF permission classes applied per viewset (`qa/permissions.py`, `accounts/permissions.py`):

| Action | anonymous | student | lecturer | admin |
| --- | --- | --- | --- | --- |
| Read lectures, questions, stats, docs | ✓ | ✓ | ✓ | ✓ |
| Ask in an open lecture, upvote | — | ✓ | ✓ | ✓ |
| Edit / delete a question | — | own | own + in own lectures | all |
| Create a lecture | — | — | ✓ (owner) | ✓ |
| Rename / open / close / delete a lecture, mark answered | — | — | own | all |
| Manage users (`/api/users/`) | — | — | — | ✓ |

Missing token → `401`, wrong role or not the owner → `403 {"detail": "Only the lecture owner or an admin can do this."}`. Every lecture/question in a response carries `can_manage` / `can_edit` / `can_answer` computed for the caller, so the frontend shows only the controls the user may use.

## Frontend

Server-rendered shells (`backend/qa/templates/qa/*.html`) with a small client in `backend/qa/static/qa/app.js`:

- stores the token pair and the user profile in `localStorage`, adds `Authorization: Bearer` to every API call, and on a `401` silently refreshes the pair and retries once (then signs the user out and redirects to `/login/?next=…`);
- renders DRF errors: `{"detail": …}` as a toast, `{"field": [...]}` under the matching inputs;
- pages: lectures list with search / filters / pagination and "Start a lecture" (lecturers), login, register, personal cabinet (profile, password, my lectures, my questions, session with the access-token expiry and a "refresh now" button), users admin table, audience page (ask with live "already asked?" hints and the predicted topic, topic chips and a topic filter, upvote, edit own), projector screen (QR code, live board with topic chips and a questions-by-topic panel, close / mark answered for the owner), **topic plan page** `/l/{code}/plan/` (topics CRUD, material upload with drag-and-drop, re-tag, per-topic summary, Markdown export);
- lecturer tools on every question: mark answered, write / edit / remove the written answer, change the topic;
- the board polls `GET /api/lectures/{code}/` every `REFRESH_SECONDS`; light / dark theme, responsive down to phone width.

## REST API

Reference with examples and the curl walk-through: **[`docs/API.md`](docs/API.md)**. Schema: [`backend/openapi.yaml`](backend/openapi.yaml) (exported from `/api/schema/`).

| Method | Endpoint | Description | Who |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register/` | Create a student or lecturer account → tokens | all |
| `POST` | `/api/auth/login/` | `{username, password}` → `{access, refresh, user}` | all |
| `POST` | `/api/auth/refresh/` | `{refresh}` → new `{access, refresh}` (old refresh revoked) | all |
| `POST` | `/api/auth/logout/` | Revoke a refresh token → 205 | signed in |
| `GET` / `PATCH` | `/api/auth/me/` | My profile with stats / edit name, email | signed in |
| `POST` | `/api/auth/me/password/` | Change password → fresh tokens | signed in |
| `GET` | `/api/users/` · `/api/users/{id}/` | List / get users (`?role=`, `?is_active=`, `?search=`) | admin |
| `PATCH` / `DELETE` | `/api/users/{id}/` | Change role / active flag · delete | admin |
| `GET` | `/api/lectures/` | List — `?is_open=`, `?owner=me`, `?search=`, `?ordering=`, `?limit=&offset=` | all |
| `POST` | `/api/lectures/` | Create (caller becomes owner) | lecturer, admin |
| `GET` | `/api/lectures/{key}/` | Retrieve by id or code, with topics and questions in screen order | all |
| `PUT` / `PATCH` / `DELETE` | `/api/lectures/{key}/` | Update / delete (cascade: topics, material, questions, upvotes, answers) | owner, admin |
| `POST` | `/api/lectures/{key}/toggle/` | Open / close | owner, admin |
| `GET` / `POST` | `/api/lectures/{key}/questions/` | List / ask (`topic_id` optional → otherwise the model tags it; 409 if closed) | all / signed in |
| `GET` / `POST` | `/api/lectures/{key}/topics/` | Topic plan / add a topic | all / owner, admin |
| `GET` / `POST` / `DELETE` | `/api/lectures/{key}/material/` | Lecture text (JSON or multipart `file`): upload builds topics and re-tags | all / owner, admin |
| `GET` | `/api/lectures/{key}/suggest/?text=` | Preview the automatic tag with a score per topic | all |
| `GET` | `/api/lectures/{key}/similar/?text=` | Similar existing questions ("already asked?") | all |
| `POST` | `/api/lectures/{key}/retag/` | Run the model again over the lecture (`?include_manual=true`) | owner, admin |
| `GET` | `/api/lectures/{key}/summary/` | Totals and questions / answers / votes per topic | all |
| `GET` | `/api/lectures/{key}/export/` | Markdown export (topics → questions → answers) | all |
| `GET` | `/api/topics/` | All topics — `?lecture=`, `?search=`, `?ordering=` | all |
| `GET` / `PUT` / `PATCH` / `DELETE` | `/api/topics/{id}/` | Retrieve / update / delete (questions keep, `topic_id` → null) | all / owner, admin |
| `GET` | `/api/topics/{id}/questions/` | Questions tagged with a topic | all |
| `GET` | `/api/questions/` | List — `?lecture=`, `?topic=`, `?is_answered=`, `?has_answer=`, `?tag_source=`, `?author=me`, `?search=`, `?ordering=` | all |
| `GET` / `PUT` / `PATCH` / `DELETE` | `/api/questions/{id}/` | Retrieve / update (`topic_id` makes the tag manual) / delete | all / author, owner, admin |
| `POST` | `/api/questions/{id}/upvote/` | Toggle the caller's upvote | signed in |
| `POST` | `/api/questions/{id}/answered/` | Toggle answered | owner, admin |
| `GET` / `PUT` / `DELETE` | `/api/questions/{id}/answer/` | Written answer: read / write or replace (201 / 200) / delete | all / owner, admin |
| `GET` | `/api/` · `/api/stats/` · `/health/` · `/api/schema/` | Root, totals, health, OpenAPI | all |

Lists are paginated (`count / next / previous / results`); errors follow DRF (`{"field": [...]}` for 400, `{"detail": "..."}` otherwise).

## Postman collection

[`postman/RaiseHand.postman_collection.json`](postman/RaiseHand.postman_collection.json) — **89 requests, 161 assertions** — plus [`postman/local.postman_environment.json`](postman/local.postman_environment.json) (`baseUrl`, `demoPassword`). Import both, select the environment and run the collection with the Runner: folder **1** registers a throw-away student and lecturer and stores their tokens in collection variables (the collection's default auth is `Bearer {{access_token}}`), shows login, the JWT claims, profile edit, refresh **rotation** and the rejected reuse of the old refresh token; **2–4** run the lecture and question CRUD as the lecturer and the student, including the `401`/`403`/`409` cases; **3b** walks through the final-project features — topics, material upload, the tagging model (auto / manual / untagged), similar questions, answers, summary, export; **5** logs out and proves the refresh token is revoked; **6** signs in as the admin, manages users and deletes the throw-away accounts; **7** shows the error formats and checks the schema. The run is repeatable.

```bash
npx newman run postman/RaiseHand.postman_collection.json -e postman/local.postman_environment.json
# → 89 requests, 161 assertions, 0 failed
```

## Data models

```text
accounts.User (AbstractUser + role: student | lecturer | admin)
   ├── Lecture.owner        (title, code, is_open, created_at)
   │      ├── LectureMaterial (lecture OneToOne CASCADE, title, text, uploaded_by → User)          1 → 1
   │      ├── Topic           (lecture FK CASCADE, title, keywords, description, order)  unique (lecture, title)   1 → N
   │      └── Question        (lecture FK CASCADE, author FK → User, topic FK SET_NULL, tag_source, tag_score,
   │             │             text, is_answered, created_at)                                                      1 → N
   │             ├── Upvote   (question FK CASCADE, user FK → User)   unique (question, user)                       1 → N
   │             └── Answer   (question OneToOne CASCADE, author FK → User SET_NULL, text, created_at, updated_at)  1 → 1
   └── token_blacklist.OutstandingToken / BlacklistedToken  (refresh tokens that can be revoked)
```

Two one-to-one relations (`LectureMaterial`, `Answer`) and four one-to-many ones, all cascading except `Question.topic`: a topic is a label on the lecture plan, so deleting a topic untags its questions instead of deleting them.

Migrations: `accounts/0001` (user), `qa/0001` (schema), `qa/0002` (demo accounts + demo lecture), `qa/0003` (topics, material, answers, tag fields), `qa/0004` (demo topics and an answer for `KBTU26`), SimpleJWT's `token_blacklist`. Applied by `entrypoint.sh` on every start.

## Automatic tagging (`backend/qa/tagging.py`, `backend/qa/material.py`)

1. Every topic is a document: title (counted twice), keywords and description — the section of the uploaded lecture text.
2. `TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))` from scikit-learn turns the topics and the new question into vectors; **cosine similarity** gives a score per topic. Character n-grams work across Russian, Kazakh and English, survive typos and word endings, and need no stemmer.
3. Each keyword found in the question adds a bonus (0.25, capped), so the lecturer's own words win.
4. The best topic is used when its score reaches `TAGGING_THRESHOLD` (0.18 by default); otherwise the question stays untagged — a wrong tag is worse than none. The score is stored as `tag_score`, the origin as `tag_source` (`auto` | `manual` | empty).
5. The same vectorizer over the lecture's existing questions powers `/similar/` ("already asked?", `SIMILAR_THRESHOLD` 0.35).

Uploading lecture text (`POST /api/lectures/{key}/material/`) splits it into sections by headings (Markdown `#`, numbered `1.`, ALL CAPS lines, PDF slide titles; paragraph groups as a fallback), extracts the distinguishing words of each section as keywords (word-level TF-IDF across sections) and creates or updates the topics; questions are re-tagged afterwards. `TAGGING_BACKEND=keywords` switches the n-gram part off for comparison. On the demo data the model agrees with a hand-written keyword rule on 48 of 52 questions and tags 103 of 104.

## Services (compose.yaml)

| Service | Image | Role | Ports | Depends on |
| --- | --- | --- | --- | --- |
| `web` | built from `backend/Dockerfile` | Django + DRF served by gunicorn; migrates, collects static files, seeds | `${WEB_PORT}:8000` | `db` must be **healthy** (`pg_isready`) |
| `db` | `postgres:17-alpine` | PostgreSQL with the named volume `pgdata` | `127.0.0.1:${DB_PORT_HOST}:5432` (host access only, optional) | — |
| `tunnel` (profile `tunnel`, optional) | `cloudflare/cloudflared:2026.10.0` | Public HTTPS address for the classroom demo (the QR code follows it automatically) | — | `web` |

Both services share the `backend` network, so the app reaches the database as `db:5432`. The project is named `raisehand-hw4`, so its containers and volume (`raisehand-hw4_pgdata`) do not collide with the earlier homeworks.

## Configuration (`.env`)

`.env` is git-ignored and excluded from the image; `.env.example` is the committed template. Compose reads it for `${VAR}` interpolation (the `db` service) and passes it to `web` via `env_file:`.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | db, web | Database name, role and password |
| `DJANGO_SECRET_KEY` | web | Django secret key **and** the JWT signing key — required, ≥ 32 characters, no default in code |
| `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | web | Debug flag (default off); allowed hosts (add your LAN IP for a demo) |
| `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS` | web | Token lifetimes (default 15 minutes / 7 days) |
| `TAGGING_BACKEND`, `TAGGING_THRESHOLD`, `SIMILAR_THRESHOLD` | web | Tagging model: `tfidf` (default) or `keywords`; minimum score for an automatic tag (0.18); minimum similarity for "already asked" hints (0.35) |
| `DEMO_PASSWORD` | web | Password of the demo accounts created by the seed (default `Demo12345!`) |
| `SEED_DEMO` | web | `1` loads the demo data set on start (idempotent), `0` keeps only the demo accounts + one lecture |
| `APP_NAME`, `PUBLIC_URL`, `REFRESH_SECONDS` | web | Header name; address for the QR code (empty = tunnel or request address); polling interval |
| `WEB_PORT`, `DB_PORT_HOST` | compose | Host ports (default 8000 / 5433) |

## Commands

```bash
docker compose ps                                   # state and health of both services
docker compose logs -f web                          # migrations, seed, then gunicorn access log
docker compose run --rm web python manage.py test   # 55 tests (auth, permissions, CRUD, topics, tagging, material, answers, docs, seed, pages)
docker compose exec web python manage.py seed_demo --clear    # regenerate the demo lectures and questions
docker compose exec db psql -U raisehand -d raisehand -c 'SELECT username, role FROM accounts_user LIMIT 10;'
docker compose exec db psql -U raisehand -d raisehand -c 'SELECT count(*) FROM token_blacklist_blacklistedtoken;'
docker compose up -d --build                        # rebuild and recreate after a code change
docker compose down                                 # keep the volume · down -v removes it (fresh database next time)
```

## Roadmap — what would make it a daily tool

Done in this version: topic plan, automatic tagging, "already asked?" hints, written answers, summary and export. Next, in the order I would build them: live updates over WebSocket (Django Channels) instead of polling; a course → lectures hierarchy with an archive and per-course statistics; quick polls ("clear / not clear") during the lecture; a Telegram bot as a second entrance for students; a sentence-embedding backend for tagging (`TAGGING_BACKEND=embeddings`) when the lecture text is long; interface in Russian / Kazakh / English; GitHub Actions running the tests and the Postman collection on every push.

## How the HW4 / endterm requirements are covered

| Requirement | Where |
| --- | --- |
| Extend the REST API into a complete web application | HW3 API + `accounts` app + frontend pages |
| Implement authentication and authorization | SimpleJWT (`accounts/api.py`, `SIMPLE_JWT` in settings): register, login, refresh with rotation + blacklist, logout; roles on `accounts.User` |
| Configure permissions for protected API operations | `qa/permissions.py` (`LecturePermission`, `QuestionPermission`), `accounts/permissions.py` (`IsAdmin`); `IsAuthenticatedOrReadOnly` default |
| Filtering, search, pagination | django-filter (`qa/filters.py`: `is_open`, `owner=me`, `lecture`, `is_answered`, `author=me`), `SearchFilter`, `OrderingFilter`, `LimitOffsetPagination` |
| Integrate the REST API with a client-side frontend | `backend/qa/static/qa/app.js` + templates: all pages read and write through `/api/…` with the Bearer token |
| Handle API requests and errors on the frontend | automatic token refresh on 401, redirect to login, field errors under inputs, toasts for `detail` errors, empty / loading states |
| Backend and database as separate services | `web` and `db` in `compose.yaml`, `backend` network, `depends_on … service_healthy` |
| Containerize with Docker and Docker Compose | `backend/Dockerfile` (non-root user, HEALTHCHECK, entrypoint), `compose.yaml`, named volume `pgdata` |
| Environment variables for configuration and sensitive settings | `.env` → `env_file:` / `${VAR}`; secrets have no defaults in code; `.env` never committed |
| Demonstrate the complete application running through Docker Compose | `docker compose up --build` → <http://localhost:8000> |
| Serializers, CRUD, validation, API client (HW3) | `qa/serializers.py`, viewsets, 55 tests, Postman collection, Swagger |
| Related models: one-to-one and one-to-many with cascade | `LectureMaterial` and `Answer` (`OneToOneField`), `Topic` (`ForeignKey`), see *Data models* |
| Automatic topic detection for questions | `qa/tagging.py` (TF-IDF + keywords), `qa/material.py` (topics from uploaded lecture text), `/suggest/`, `/similar/`, `/retag/` |

## Project structure

```text
hw4/
├── compose.yaml, .env.example, .gitignore, README.md
├── docs/API.md                 # endpoint reference, auth walk-through
├── postman/                    # collection (89 requests) + environment
└── backend/
    ├── Dockerfile, entrypoint.sh, .dockerignore, requirements.txt, openapi.yaml, manage.py
    ├── config/                 # settings (AUTH_USER_MODEL, REST_FRAMEWORK, SIMPLE_JWT, SPECTACULAR_SETTINGS), urls, wsgi
    ├── accounts/
    │   ├── models.py           # User(AbstractUser) + role, display_name, is_admin / is_lecturer
    │   ├── serializers.py      # register, login (JWT claims), profile, password change, admin user
    │   ├── permissions.py      # IsAdmin, ReadOnly, role helpers
    │   ├── api.py              # /api/auth/* and /api/users/
    │   └── urls.py
    └── qa/
        ├── models.py           # Lecture(owner) → Topic, LectureMaterial, Question(author, topic) → Upvote(user), Answer
        ├── serializers.py      # lecture / topic / material / question / answer shapes with can_manage / can_edit / can_answer
        ├── permissions.py      # LecturePermission, TopicPermission, QuestionPermission
        ├── api.py              # viewsets, actions (topics, material, suggest, similar, retag, summary, export, answer), stats, health, root
        ├── tagging.py          # TF-IDF + keyword tagging model, similar questions, re-tagging
        ├── material.py         # lecture text → sections (headings) → topics with keywords; .txt / .md / .pdf
        ├── export.py           # Markdown export of a lecture
        ├── filters.py, pagination.py, lookup.py, links.py, tunnel.py, views.py, urls.py
        ├── management/commands/   # wait_for_db.py, seed_demo.py (accounts, topics, tagged questions, answers)
        ├── migrations/         # 0001 schema, 0002 demo accounts + lecture, 0003 topics/material/answers, 0004 demo topics
        ├── static/qa/          # app.css (design system, light/dark), app.js (JWT client, rendering, ask assistant)
        ├── templates/qa/       # base, home, login, register, cabinet, users, lecture, screen, plan
        └── tests.py            # 55 tests
```
