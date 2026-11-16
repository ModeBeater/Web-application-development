# Raise Hand — REST API reference (HW3, Django REST Framework)

Version 2.1: adds **topics** (Lecture 1→\* Topic, Topic 1→\* Question) and **answers** (Question 1→1 Answer).

Base URL: `http://localhost:8000` (the `WEB_PORT` from `.env`).

Three ways to read this API:

| Where | What |
|---|---|
| **http://localhost:8000/docs/** | Swagger UI rendered from the schema that drf-spectacular generates from the code; "Try it out" sends real requests |
| `http://localhost:8000/api/schema/` (`?format=json` for JSON) | The OpenAPI 3 schema itself; a committed copy is [`backend/openapi.yaml`](../backend/openapi.yaml) (`python manage.py spectacular --file openapi.yaml`) |
| `http://localhost:8000/api/lectures/` in a browser | DRF's **browsable API**: the same endpoints rendered as HTML with forms for POST/PUT/PATCH/DELETE |

Ready-made requests: [`postman/RaiseHand.postman_collection.json`](../postman/RaiseHand.postman_collection.json).

## Conventions

| Topic | Rule |
|---|---|
| Format | Request and response bodies are JSON. Send `Content-Type: application/json`. |
| Lecture key | `{key}` is the numeric **id** (`12`) **or** the 6-character **join code** (`KBTU26`, case-insensitive). |
| Question / topic id | `{id}` is the numeric id only. |
| Lists | Paginated: `{"count": 107, "next": "…?limit=50&offset=50", "previous": null, "results": [...]}`. Page with `?limit=` (default 50, max 500) and `?offset=`. |
| Filters | `?is_open=true|false` (lectures); `?lecture=<id|code>`, `?topic=<id>`, `?is_answered=true|false`, `?has_answer=true|false` (questions); `?lecture=<id|code>` (topics) — django-filter |
| Search | `?search=` — case-insensitive, lectures: title and code; questions: text and author; topics: title and keywords |
| Ordering | `?ordering=field` or `-field`: lectures `created_at`, `title`, `question_count`; questions `created_at`, `votes`, `is_answered`; topics `order`, `title`, `question_count`, `created_at` |
| Success codes | `200 OK` read/update · `201 Created` create · `204 No Content` delete (empty body) |
| Error codes | `400` validation · `404` unknown id/code · `405` wrong method · `409` lecture closed · `503` database down |
| Error body | validation: `{"title": ["Title must be at least 3 characters."]}` (field → messages); everything else: `{"detail": "…"}` |
| Text fields | whitespace trimmed and collapsed by the serializers; limits: title 3–120, text 1–500, author ≤ 40, topic keywords ≤ 300 (lower-cased, comma-separated), answer 1–2000 |
| Timestamps | ISO 8601 with offset in the project time zone (`Asia/Almaty`), e.g. `2026-10-28T23:34:13+05:00` |
| Auth | none yet (HW4) — every endpoint is open |
| Voter | upvotes are per *voter*: the `voter` cookie (set automatically) or an explicit `"voter"` value in the body |

## Endpoint overview

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET | `/api/` | API root: version and links | 200 |
| GET | `/health/` | App + database health (Docker `HEALTHCHECK`) | 200 / 503 |
| GET | `/api/schema/` | OpenAPI 3 schema (YAML; `?format=json`) | 200 |
| **Lectures** | | | |
| GET | `/api/lectures/` | List lectures (`?is_open=`, `?search=`, `?ordering=`, `?limit=&offset=`) | 200 |
| POST | `/api/lectures/` | Create a lecture | 201 |
| GET | `/api/lectures/{key}/` | Get one lecture **with its topics and questions** (screen order) | 200 |
| PUT | `/api/lectures/{key}/` | Replace (title required) | 200 |
| PATCH | `/api/lectures/{key}/` | Partial update (any of title, is_open) | 200 |
| DELETE | `/api/lectures/{key}/` | Delete lecture + its topics, questions, upvotes and answers (cascade) | 204 |
| POST | `/api/lectures/{key}/toggle/` | Open ⇄ close the lecture | 200 |
| **Topics** (one lecture → many topics) | | | |
| GET | `/api/lectures/{key}/topics/` | Topics of one lecture in plan order, with question counts (paginated) | 200 |
| POST | `/api/lectures/{key}/topics/` | Add a topic to the lecture (title unique within the lecture) | 201 |
| GET | `/api/topics/` | All topics (`?lecture=`, `?search=`, `?ordering=`, `?limit=&offset=`) | 200 |
| GET | `/api/topics/{id}/` | Get one topic | 200 |
| PUT | `/api/topics/{id}/` | Replace (title required) | 200 |
| PATCH | `/api/topics/{id}/` | Partial update (title, keywords, order) | 200 |
| DELETE | `/api/topics/{id}/` | Delete the topic; its questions stay with `topic_id = null` | 204 |
| GET | `/api/topics/{id}/questions/` | Questions tagged with the topic, screen order (paginated) | 200 |
| **Questions** | | | |
| GET | `/api/lectures/{key}/questions/` | Questions of one lecture, screen order (paginated) | 200 |
| POST | `/api/lectures/{key}/questions/` | Ask (create) a question in the lecture, optionally tagged with `topic_id` | 201 / 409 |
| GET | `/api/questions/` | All questions (`?lecture=`, `?topic=`, `?is_answered=`, `?has_answer=`, `?search=`, `?ordering=`, `?limit=&offset=`) | 200 |
| GET | `/api/questions/{id}/` | Get one question | 200 |
| PUT | `/api/questions/{id}/` | Replace (text required) | 200 |
| PATCH | `/api/questions/{id}/` | Partial update (any of text, author, is_answered, topic_id) | 200 |
| DELETE | `/api/questions/{id}/` | Delete question + its upvotes and answer (cascade) | 204 |
| POST | `/api/questions/{id}/upvote/` | Toggle the caller's upvote | 200 |
| POST | `/api/questions/{id}/answered/` | Toggle the answered flag | 200 |
| **Answer** (one question → one answer) | | | |
| GET | `/api/questions/{id}/answer/` | The written answer | 200 / 404 |
| PUT | `/api/questions/{id}/answer/` | Write (201) or replace (200) the answer; marks the question answered | 201 / 200 |
| DELETE | `/api/questions/{id}/answer/` | Delete the answer and reopen the question | 204 / 404 |

30 endpoints in total (3 service + 7 lectures + 8 topics + 12 questions and answers).

## Data model

```text
Lecture ──1:N──▶ Topic          lecture.topics      ON DELETE CASCADE
Lecture ──1:N──▶ Question       lecture.questions   ON DELETE CASCADE
Topic   ──1:N──▶ Question       topic.questions     ON DELETE SET NULL  (a topic is a label, not an owner)
Question ─1:N──▶ Upvote         question.upvotes    ON DELETE CASCADE   unique (question, voter_id)
Question ─1:1──▶ Answer         question.answer     ON DELETE CASCADE   OneToOneField
```

## Objects (serializers)

### Lecture — `LectureSerializer`

```json
{
  "id": 1,
  "title": "Flutter 1 · Lecture 00 · Course introduction",
  "code": "KBTU26",
  "is_open": true,
  "question_count": 3,
  "topic_count": 3,
  "created_at": "2026-10-28T23:34:13+05:00",
  "join_url": "http://localhost:8000/l/KBTU26/",
  "screen_url": "http://localhost:8000/l/KBTU26/screen/"
}
```

Writable: `title` (3–120 characters, required), `is_open` (boolean, default `true`). Read-only: everything else — `code` is generated by the server, `question_count` and `topic_count` come from database annotations, the URLs are computed (`PUBLIC_URL` from `.env`, else the running Cloudflare tunnel, else the request address). `GET /api/lectures/{key}/` uses `LectureDetailSerializer`, which adds `"topics": [Topic, …]` and `"questions": [Question, …]`.

### Topic — `TopicSerializer`

```json
{
  "id": 1,
  "lecture_id": 1,
  "lecture_code": "KBTU26",
  "title": "Dart language",
  "keywords": "dart, language, syntax, null safety",
  "order": 1,
  "question_count": 1,
  "created_at": "2026-11-16T12:00:00+05:00"
}
```

Writable: `title` (3–120, required, unique within the lecture — case-insensitive), `keywords` (≤ 300, comma-separated, normalized to lower case), `order` (position in the lecture plan). Read-only: `id`, `lecture_id`, `lecture_code`, `question_count`, `created_at`. The lecture comes from the URL (`POST /api/lectures/{key}/topics/`) and cannot be changed afterwards.

### Answer — `AnswerSerializer`

```json
{
  "id": 1,
  "question_id": 2,
  "text": "You can write and test the code on Windows, but the iOS build itself needs Xcode…",
  "author": "Nurkhan Tashimov",
  "created_at": "2026-11-16T12:00:00+05:00",
  "updated_at": "2026-11-16T12:05:00+05:00"
}
```

Writable: `text` (1–2000, required), `author` (≤ 40, optional). Exactly one answer per question (`OneToOneField`); it is embedded in the Question as `"answer"` and is `null` while the question has none.

### Question — `QuestionSerializer`

```json
{
  "id": 1,
  "lecture_id": 1,
  "lecture_code": "KBTU26",
  "topic_id": 1,
  "topic_title": "Dart language",
  "text": "Do I need to know Dart well before starting with Flutter?",
  "author": "Aigerim",
  "votes": 2,
  "voted": false,
  "is_answered": false,
  "answer": null,
  "created_at": "2026-10-28T23:34:13+05:00"
}
```

Writable: `text` (1–500, required), `author` (≤ 40, optional, shown as `"Anonymous"` when empty), `is_answered` (boolean), `topic_id` (id of a topic **of the same lecture**, or `null`; another lecture's topic → `400 {"topic_id": ["This topic belongs to another lecture."]}`), and the write-only `voter` (≤ 36, optional). Read-only: `id`, `lecture_id`, `lecture_code`, `topic_title`, `votes`, `voted`, `answer`, `created_at`.

---

## Service

### GET /api/

```json
{
  "name": "Raise Hand API",
  "version": "2.0",
  "docs": "http://localhost:8000/docs/",
  "schema": "http://localhost:8000/api/schema/",
  "health": "http://localhost:8000/health/",
  "lectures": "http://localhost:8000/api/lectures/",
  "questions": "http://localhost:8000/api/questions/"
}
```

### GET /health/

`200` → `{"status": "ok", "database": "PostgreSQL 17.6"}` · `503` → `{"status": "error", "database": "connection refused …"}`

---

## Lectures

### GET /api/lectures/ — list

```http
GET /api/lectures/?search=flutter&is_open=true&ordering=title&limit=2
```
```json
{
  "count": 9,
  "next": "http://localhost:8000/api/lectures/?is_open=true&limit=2&offset=2&ordering=title&search=flutter",
  "previous": null,
  "results": [ { "id": 1, "title": "Flutter 1 · Lecture 00 · Course introduction", "code": "KBTU26", "is_open": true, "question_count": 3, "…": "…" }, { "…": "…" } ]
}
```

### POST /api/lectures/ — create

```http
POST /api/lectures/
Content-Type: application/json

{"title": "Flutter 1 · Lecture 09 · State management"}
```
`201 Created` → the Lecture object with the freshly generated `code`.
`400` → `{"title": ["This field is required."]}` or `{"title": ["Title must be at least 3 characters."]}`.

### GET /api/lectures/{key}/ — get by id or code

`GET /api/lectures/1/` and `GET /api/lectures/kbtu26/` return the same lecture, plus `"questions": [...]` ordered like the projector screen (most upvoted first, answered at the bottom). The response sets the `voter` cookie.
`404` → `{"detail": "No lecture with id or code '999'."}`

### PUT /api/lectures/{key}/ — replace

```http
PUT /api/lectures/1/
Content-Type: application/json

{"title": "Flutter 1 · Lecture 00 · Course introduction (updated)", "is_open": true}
```
`title` is required (that is what makes it a PUT in DRF); `is_open` keeps its value when omitted. Read-only fields in the body (`code`, `id`) are ignored.

### PATCH /api/lectures/{key}/ — partial update

```http
PATCH /api/lectures/1/
Content-Type: application/json

{"is_open": false}
```

### DELETE /api/lectures/{key}/ — delete

`204 No Content`. The lecture's questions and their upvotes are deleted too (`on_delete=CASCADE`). A second delete returns `404`.

### POST /api/lectures/{key}/toggle/ — open / close

No body. `200` → `{"id": 1, "code": "KBTU26", "is_open": false}`. A closed lecture answers `409` to new questions.

---

## Topics

### GET /api/lectures/{key}/topics/ — topics of one lecture

Paginated, plan order (`order`, then id): `{"count": 3, "next": null, "previous": null, "results": [Topic, …]}`. `404` for an unknown lecture.

### POST /api/lectures/{key}/topics/ — add a topic

```http
POST /api/lectures/KBTU26/topics/
Content-Type: application/json

{"title": "Hot reload", "keywords": "hot reload, restart", "order": 4}
```
`201 Created` → the Topic. `400` → `{"title": ["This field is required."]}`, `{"title": ["Title must be at least 3 characters."]}` or `{"title": ["This lecture already has a topic with that title."]}`.

### GET /api/topics/ — list all

```http
GET /api/topics/?lecture=KBTU26&ordering=-question_count
```
`?lecture=<id|code>` (404 if unknown), `?search=` over title and keywords, `?ordering=order|title|question_count|created_at`, `?limit=&offset=`.

### GET /api/topics/{id}/ — get by id

`200` → the Topic. `404` → `{"detail": "No Topic matches the given query."}`

### PUT / PATCH /api/topics/{id}/ — update

```http
PATCH /api/topics/1/
Content-Type: application/json

{"keywords": "dart, null safety, late"}
```
`PUT` requires `title`; `keywords` and `order` keep their values when omitted. The lecture cannot be changed.

### DELETE /api/topics/{id}/ — delete

`204 No Content`. Questions tagged with the topic are **kept** — their `topic_id` becomes `null` (`on_delete=SET_NULL`), because a topic is a label on the lecture plan, not the owner of the audience's questions.

### GET /api/topics/{id}/questions/ — questions of a topic

Paginated, screen order (most upvoted first, answered last) — the same shape as `/api/lectures/{key}/questions/`. The equivalent filter on the global list is `GET /api/questions/?topic=<id>`.

---

## Questions

### GET /api/lectures/{key}/questions/ — questions of one lecture

Paginated, screen order: `{"count": 3, "next": null, "previous": null, "results": [Question, …]}`.

### POST /api/lectures/{key}/questions/ — ask (create)

```http
POST /api/lectures/KBTU26/questions/
Content-Type: application/json

{"text": "Is EXPOSE enough to publish a port?", "author": "Yevgeniy", "topic_id": 3}
```
`201 Created` → the Question. `400` → `{"text": ["This field is required."]}` or `{"topic_id": ["This topic belongs to another lecture."]}`. `409` → `{"detail": "This lecture is closed for new questions."}`. `topic_id` is optional.

### GET /api/questions/ — list all

```http
GET /api/questions/?lecture=KBTU26&limit=1
```
```json
{
  "count": 3,
  "next": "http://localhost:8000/api/questions/?lecture=KBTU26&limit=1&offset=1",
  "previous": null,
  "results": [
    { "id": 3, "lecture_id": 1, "lecture_code": "KBTU26", "topic_id": 2, "topic_title": "Tooling and setup",
      "text": "Which IDE should I use: VS Code or Android Studio?", "author": "Daniyar",
      "votes": 0, "voted": false, "is_answered": false, "answer": null, "created_at": "2026-10-28T23:34:13+05:00" }
  ]
}
```
Newest first by default; `?ordering=-votes` for the most wanted, `?is_answered=false` for open ones, `?topic=2` for one topic, `?has_answer=true` for questions with a written answer, `?search=docker` for text/author.
`?lecture=NOPE42` → `404`; `?topic=abc` → `400 {"topic": ["Enter a number."]}`.

### GET /api/questions/{id}/ — get by id

`200` → the Question. `404` → `{"detail": "No Question matches the given query."}`

### PUT / PATCH /api/questions/{id}/ — update

```http
PATCH /api/questions/1/
Content-Type: application/json

{"is_answered": true}
```
`PUT` requires `text`; `author`, `is_answered` and `topic_id` keep their values when omitted. `{"topic_id": null}` removes the tag.

### DELETE /api/questions/{id}/ — delete

`204 No Content`; the question's upvotes and its answer go with it (cascade).

### POST /api/questions/{id}/upvote/ — toggle upvote

Optional body `{"voter": "any-string"}`; without it the `voter` cookie is used (and created on first call). First call adds the vote, the second call from the same voter removes it.
`200` → `{"id": 1, "votes": 3, "voted": true}`

### POST /api/questions/{id}/answered/ — toggle answered

No body. `200` → `{"id": 1, "is_answered": true}`. This is the quick flag used from the projector screen; the written answer below is separate.

---

## Answer (one-to-one)

### GET /api/questions/{id}/answer/

`200` → the Answer. `404` → `{"detail": "This question has no answer yet."}` (or `No Question matches the given query.` for an unknown question).

### PUT /api/questions/{id}/answer/ — write or replace

```http
PUT /api/questions/2/answer/
Content-Type: application/json

{"text": "The iOS build needs Xcode, so a Mac or a macOS CI runner is required.", "author": "Nurkhan Tashimov"}
```
`201 Created` the first time, `200 OK` when an answer already existed (it is replaced — still one row per question). In both cases the question's `is_answered` becomes `true`. `400` → `{"text": ["This field may not be blank."]}`.

### DELETE /api/questions/{id}/answer/

`204 No Content` and the question's `is_answered` becomes `false`; `404` when there is no answer.

---

## curl cheat-sheet

```bash
B=http://localhost:8000
curl $B/api/lectures/                                                   # list (paginated)
curl -X POST $B/api/lectures/ -H 'Content-Type: application/json' \
     -d '{"title":"Demo lecture"}'                                      # create  -> note the id
curl $B/api/lectures/1/                                                 # get by id (or /KBTU26/)
curl -X PATCH $B/api/lectures/1/ -H 'Content-Type: application/json' \
     -d '{"is_open":false}'                                             # update
curl -X POST $B/api/lectures/1/questions/ -H 'Content-Type: application/json' \
     -d '{"text":"Why Compose?","author":"Me"}'                         # create question
curl "$B/api/questions/?ordering=-votes&limit=5"                        # most wanted questions
curl -X POST $B/api/lectures/1/topics/ -H 'Content-Type: application/json' \
     -d '{"title":"Compose basics","keywords":"compose, service, volume"}'   # topic (one-to-many)
curl "$B/api/topics/?lecture=1"                                         # topics of the lecture
curl -X PATCH $B/api/questions/1/ -H 'Content-Type: application/json' \
     -d '{"topic_id":1}'                                                # tag a question
curl -X PUT $B/api/questions/1/answer/ -H 'Content-Type: application/json' \
     -d '{"text":"Because Compose wires the containers together.","author":"Me"}'   # answer (one-to-one)
curl -X DELETE $B/api/questions/1/ -i                                   # delete -> 204 (upvotes + answer cascade)
curl -X DELETE $B/api/lectures/1/ -i                                    # delete -> 204
```
