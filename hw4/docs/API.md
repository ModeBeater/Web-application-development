# Raise Hand — REST API reference (HW4 / endterm · final: DRF + JWT + topics & tagging)

Base URL: `http://localhost:8000` (the `WEB_PORT` from `.env`).

| Where | What |
|---|---|
| **http://localhost:8000/docs/** | Swagger UI generated from the code (drf-spectacular). Click **Authorize**, paste an access token, and "Try it out" works as that user |
| `http://localhost:8000/api/schema/` (`?format=json`) | The OpenAPI 3 schema; committed copy: [`backend/openapi.yaml`](../backend/openapi.yaml) |
| `http://localhost:8000/api/lectures/` in a browser | DRF's browsable API (read-only without a token — the browser has no Bearer header) |
| [`postman/RaiseHand.postman_collection.json`](../postman/RaiseHand.postman_collection.json) | 89 requests that walk through registration, the token lifecycle, every CRUD operation, every role rule, and the topics / tagging / answers flow |

## Authentication (JWT)

```http
POST /api/auth/login/
Content-Type: application/json

{"username": "student", "password": "Demo12345!"}
```
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9…",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9…",
  "user": { "id": 5, "username": "student", "display_name": "Demo Student", "role": "student", "email": "student@example.com",
            "first_name": "Demo", "last_name": "Student", "is_active": true, "date_joined": "2026-10-29T16:32:46+05:00",
            "last_login": "2026-10-29T16:45:34+05:00",
            "stats": { "lectures": 0, "questions": 1, "upvotes_given": 1, "upvotes_received": 1 } }
}
```

| Token | Lifetime | Use |
|---|---|---|
| `access` | 15 min (`JWT_ACCESS_MINUTES`) | Send with every request: `Authorization: Bearer <access>`. Carries the claims `user_id`, `username`, `role`, `exp`. |
| `refresh` | 7 days (`JWT_REFRESH_DAYS`) | `POST /api/auth/refresh/ {"refresh": "…"}` → a **new access and a new refresh** token. The used refresh token is blacklisted (rotation), so each one works once. `POST /api/auth/logout/` blacklists it explicitly. |

Both tokens are signed with `DJANGO_SECRET_KEY` (HMAC-SHA256) and verified without a database lookup; only refresh tokens are stored (outstanding + blacklist tables) so they can be revoked.

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| POST | `/api/auth/register/` | `username`, `password`, `role` (`student`\|`lecturer`), optional `email`, `first_name`, `last_name` | 201 `{access, refresh, user}` | 400 per-field (`password` validators, taken `username`, `role: admin` rejected) |
| POST | `/api/auth/login/` | `username`, `password` | 200 `{access, refresh, user}` | 401 `{"detail": "No active account found with the given credentials"}` |
| POST | `/api/auth/refresh/` | `refresh` | 200 `{access, refresh}` | 401 `{"detail": "Token is blacklisted", "code": "token_not_valid"}` |
| POST | `/api/auth/logout/` 🔒 | `refresh` | 205 (empty) | 400 invalid token |
| GET | `/api/auth/me/` 🔒 | — | 200 user with `stats` | 401 |
| PATCH | `/api/auth/me/` 🔒 | `first_name`, `last_name`, `email` (role is read-only) | 200 user | 400 |
| POST | `/api/auth/me/password/` 🔒 | `current_password`, `new_password` | 200 `{access, refresh, user}` (fresh tokens) | 400 |

🔒 = requires `Authorization: Bearer <access>`. Without a token: `401 {"detail": "Authentication credentials were not provided."}`; with an expired or revoked one: `401 {"detail": "Given token not valid for any token type", "code": "token_not_valid", …}`.

## Roles and permissions

| Action | anonymous | student | lecturer | admin |
|---|---|---|---|---|
| Read lectures, topics, questions, answers, summary, export, stats, docs; `/suggest/` and `/similar/` previews | ✓ | ✓ | ✓ | ✓ |
| Ask a question in an open lecture (optionally choosing its topic), upvote | — | ✓ | ✓ | ✓ |
| Edit / delete a question, change its topic | — | own | own + in own lectures | all |
| Create a lecture | — | — | ✓ (becomes owner) | ✓ |
| Rename / open / close / delete a lecture, mark questions answered, **write answers**, **manage topics**, **upload material**, **re-tag** | — | — | own lectures | all |
| List users, change roles, deactivate, delete users | — | — | — | ✓ |

A signed-in user that is not allowed gets `403 {"detail": "Only the lecture owner or an admin can do this."}`; every response carries the flags `can_manage` (lecture) and `can_edit` / `can_answer` (question) computed for the caller, so clients can show the right controls. The rules live in `qa/permissions.py` and `accounts/permissions.py`.

## Conventions

| Topic | Rule |
|---|---|
| Format | JSON in and out; send `Content-Type: application/json` |
| Lecture key | `{key}` is the numeric **id** or the 6-character **join code** (`KBTU26`, case-insensitive); topics, questions and users by id |
| Lists | Paginated `{"count", "next", "previous", "results"}`; `?limit=` (default 50, max 500) and `?offset=` |
| Filters | lectures `?is_open=`, `?owner=<id|me>`; topics `?lecture=<id|code>`; questions `?lecture=<id|code>`, `?topic=<id>`, `?is_answered=`, `?has_answer=`, `?tag_source=manual|auto|none`, `?author=<id|me>`; users `?role=`, `?is_active=` |
| Search / ordering | `?search=` (lectures: title, code, owner name; topics: title, keywords; questions: text, author name; users: username, names, email) · `?ordering=field` / `-field` |
| Status codes | 200 read/update · 201 created (also the first `PUT …/answer/`) · 204 deleted · 205 logged out · 400 validation · 401 no/invalid token · 403 forbidden by role/ownership · 404 · 405 · 409 lecture closed · 503 database down |
| Errors | validation `{"field": ["message"]}`; everything else `{"detail": "…"}` (+ `"code"` for token errors) |
| Timestamps | ISO 8601, `Asia/Almaty` offset, e.g. `2026-10-29T16:32:46+05:00` |

## Endpoints

| Method | Path | Purpose | Who |
|---|---|---|---|
| GET | `/api/` | API root: version, links (incl. `auth.*`) | all |
| GET | `/health/` | App + database health (Docker `HEALTHCHECK`) | all |
| GET | `/api/stats/` | Totals: lectures, open_lectures, questions, answered, upvotes, users | all |
| GET | `/api/schema/` | OpenAPI 3 schema | all |
| **Lectures** | | | |
| GET | `/api/lectures/` | List (paginated, filters, search, ordering) | all |
| POST | `/api/lectures/` | Create `{"title", "is_open"?}` → 201 | lecturer, admin |
| GET | `/api/lectures/{key}/` | One lecture **with its topics and questions** (screen order) | all |
| PUT / PATCH | `/api/lectures/{key}/` | Update `title`, `is_open` | owner, admin |
| DELETE | `/api/lectures/{key}/` | Delete with its topics, material, questions, upvotes and answers → 204 | owner, admin |
| POST | `/api/lectures/{key}/toggle/` | Open ⇄ close → `{id, code, is_open}` | owner, admin |
| **Topics, material, tagging** (final project) | | | |
| GET | `/api/lectures/{key}/topics/` | The topic plan in order, with `question_count` (paginated) | all |
| POST | `/api/lectures/{key}/topics/` | Add a topic `{"title", "keywords"?, "description"?, "order"?}` → 201 | owner, admin |
| GET | `/api/topics/` | All topics (`?lecture=`, `?search=`, `?ordering=order|title|question_count`) | all |
| GET | `/api/topics/{id}/` | One topic | all |
| PUT / PATCH | `/api/topics/{id}/` | Update `title`, `keywords`, `description`, `order` | owner, admin |
| DELETE | `/api/topics/{id}/` | Delete the topic; its questions stay with `topic_id = null` → 204 | owner, admin |
| GET | `/api/topics/{id}/questions/` | Questions tagged with the topic, screen order (paginated) | all |
| GET | `/api/lectures/{key}/material/` | The uploaded lecture text (404 while none) | all |
| POST | `/api/lectures/{key}/material/` | Upload: JSON `{"title", "text", "extract"?}` or multipart `file` (.txt/.md/.pdf ≤ 5 MB) → 201 / 200; builds topics from headings and re-tags | owner, admin |
| DELETE | `/api/lectures/{key}/material/` | Remove the material (topics stay) → 204 | owner, admin |
| GET | `/api/lectures/{key}/suggest/?text=` | What the model would tag `text` with: `{topic_id, topic_title, score, threshold, scores[]}` | all |
| GET | `/api/lectures/{key}/similar/?text=` | Existing questions similar to `text`: `[{question, similarity}]` | all |
| POST | `/api/lectures/{key}/retag/` | Re-run the model (`?include_manual=true` to redo manual tags) → `{processed, tagged, untagged, topics}` | owner, admin |
| GET | `/api/lectures/{key}/summary/` | Totals + per-topic breakdown (`topics[]` ends with the `No topic` bucket) | all |
| GET | `/api/lectures/{key}/export/` | `text/markdown` document: topics → questions → answers | all |
| **Questions** | | | |
| GET | `/api/lectures/{key}/questions/` | Questions of one lecture, screen order (paginated) | all |
| POST | `/api/lectures/{key}/questions/` | Ask `{"text", "topic_id"?}` → 201 (no `topic_id` → the model tags it); 409 if closed | any signed-in user |
| GET | `/api/questions/` | All questions (filters incl. `?topic=`, `?has_answer=`, `?tag_source=`, search, ordering, pagination) | all |
| GET | `/api/questions/{id}/` | One question | all |
| PUT / PATCH | `/api/questions/{id}/` | Update `text`, `topic_id` (→ `tag_source: manual`; `null` untags), `is_answered` (owner/admin) | author, lecture owner, admin |
| DELETE | `/api/questions/{id}/` | Delete with its upvotes and answer → 204 | author, lecture owner, admin |
| POST | `/api/questions/{id}/upvote/` | Toggle the caller's upvote → `{id, votes, voted}` | any signed-in user |
| POST | `/api/questions/{id}/answered/` | Toggle answered → `{id, is_answered}` | lecture owner, admin |
| GET | `/api/questions/{id}/answer/` | The written answer (404 while none) | all |
| PUT | `/api/questions/{id}/answer/` | `{"text"}` → 201 created / 200 replaced; caller becomes the author, question marked answered | lecture owner, admin |
| DELETE | `/api/questions/{id}/answer/` | Remove the answer and reopen the question → 204 | lecture owner, admin |
| **Users** | | | |
| GET | `/api/users/` | List users (`?role=`, `?is_active=`, `?search=`, `?ordering=`) | admin |
| GET | `/api/users/{id}/` | One user with stats | admin |
| PATCH | `/api/users/{id}/` | Change `role`, `is_active`, names, email (not your own role/active) | admin |
| DELETE | `/api/users/{id}/` | Delete a user and everything they created (not yourself) | admin |

## Objects

### Lecture

```json
{
  "id": 1,
  "title": "Flutter 1 · Lecture 00 · Course introduction",
  "code": "KBTU26",
  "is_open": true,
  "owner": { "id": 2, "username": "lecturer", "display_name": "Nurkhan Tashimov", "role": "lecturer" },
  "question_count": 3,
  "topic_count": 3,
  "has_material": false,
  "created_at": "2026-10-29T16:32:46+05:00",
  "join_url": "http://localhost:8000/l/KBTU26/",
  "screen_url": "http://localhost:8000/l/KBTU26/screen/",
  "can_manage": false
}
```

Writable: `title` (3–120), `is_open`. `owner` is the creator; `can_manage` is computed for the caller. `GET /api/lectures/{key}/` adds `"topics": [Topic, …]` and `"questions": [Question, …]`.

### Topic

```json
{
  "id": 1, "lecture_id": 1, "lecture_code": "KBTU26",
  "title": "Dart language",
  "keywords": "dart, language, syntax, null safety",
  "description": "",
  "order": 1,
  "question_count": 1,
  "created_at": "2026-11-16T12:00:00+05:00"
}
```

Writable: `title` (3–120, unique within the lecture, case-insensitive), `keywords` (≤ 300, comma-separated, lower-cased), `description` (the section text when the topic came from the material), `order` (defaults to the end of the plan). The lecture is fixed by the URL the topic was created with.

### LectureMaterial

```json
{
  "id": 1, "lecture_id": 3, "title": "lecture-03-state-management.md",
  "text": "# Flutter 1 · Lecture 03 …", "characters": 1532,
  "uploaded_by": { "id": 2, "username": "lecturer", "display_name": "Nurkhan Tashimov", "role": "lecturer" },
  "created_at": "…", "updated_at": "…"
}
```

One per lecture. `POST …/material/` answers with `{"material", "topics_created", "topics_updated", "topics": [Topic, …], "retag": {"processed", "tagged", "untagged", "topics"}}`.

### Answer

```json
{
  "id": 1, "question_id": 2,
  "text": "You can write and test the code on Windows, but the iOS build itself needs Xcode…",
  "author": { "id": 2, "username": "lecturer", "display_name": "Nurkhan Tashimov", "role": "lecturer" },
  "created_at": "…", "updated_at": "…"
}
```

One per question (`OneToOneField`); embedded in the Question as `"answer"` (or `null`).

### Question

```json
{
  "id": 1,
  "lecture_id": 1,
  "lecture_code": "KBTU26",
  "lecture_title": "Flutter 1 · Lecture 00 · Course introduction",
  "topic_id": 1,
  "topic_title": "Dart language",
  "tag_source": "auto",
  "tag_score": 0.74,
  "text": "Do I need to know Dart well before starting with Flutter?",
  "author": { "id": 3, "username": "aigerim", "display_name": "Aigerim S.", "role": "student" },
  "votes": 2,
  "voted": false,
  "is_answered": false,
  "answer": null,
  "created_at": "2026-10-29T16:32:46+05:00",
  "can_edit": false,
  "can_answer": false
}
```

Writable: `text` (1–500), `topic_id` (a topic of the same lecture or `null`; sending it makes `tag_source` `manual`, omitting it on create lets the model decide → `auto` with `tag_score`, or untagged), `is_answered` (owner/admin). `author` is the signed-in user who asked; `voted`, `can_edit`, `can_answer` are computed for the caller; `answer` is the embedded written answer or `null`.

### User (`/api/auth/me/`, `/api/users/`)

`id`, `username`, `email`, `first_name`, `last_name`, `display_name`, `role`, `is_active`, `date_joined`, `last_login`, `stats {lectures, questions, upvotes_given, upvotes_received}`. Inside other objects only `id`, `username`, `display_name`, `role` are embedded.

## Walk-through with curl

```bash
B=http://localhost:8000
# 1. sign in as the demo lecturer, keep the tokens
TOKENS=$(curl -s -X POST $B/api/auth/login/ -H 'Content-Type: application/json' -d '{"username":"lecturer","password":"Demo12345!"}')
ACCESS=$(echo $TOKENS | python3 -c 'import sys,json;print(json.load(sys.stdin)["access"])')
REFRESH=$(echo $TOKENS | python3 -c 'import sys,json;print(json.load(sys.stdin)["refresh"])')

# 2. create a lecture (lecturer only) and read it back by id or code
curl -s -X POST $B/api/lectures/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' -d '{"title":"Endterm demo"}'
curl -s $B/api/lectures/?owner=me -H "Authorization: Bearer $ACCESS"

# 3. as a student: ask and upvote (403 when trying to close the lecture)
STUDENT=$(curl -s -X POST $B/api/auth/login/ -H 'Content-Type: application/json' -d '{"username":"student","password":"Demo12345!"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access"])')
curl -s -X POST $B/api/lectures/KBTU26/questions/ -H "Authorization: Bearer $STUDENT" -H 'Content-Type: application/json' -d '{"text":"Does the refresh token rotate?"}'
curl -s -X POST $B/api/questions/1/upvote/ -H "Authorization: Bearer $STUDENT"
curl -s -X POST $B/api/lectures/KBTU26/toggle/ -H "Authorization: Bearer $STUDENT"      # 403

# 4. topics, tagging, answers (lecturer token)
curl -s -X POST $B/api/lectures/KBTU26/topics/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' -d '{"title":"Hot reload","keywords":"hot reload, restart"}'
curl -s -X POST $B/api/lectures/KBTU26/material/ -H "Authorization: Bearer $ACCESS" -F "file=@lecture.md"          # topics from headings + re-tag
curl -s "$B/api/lectures/KBTU26/suggest/?text=Does%20hot%20reload%20keep%20the%20state%3F"                          # preview the tag
curl -s -X POST $B/api/lectures/KBTU26/questions/ -H "Authorization: Bearer $STUDENT" -H 'Content-Type: application/json' -d '{"text":"Does hot reload keep the state?"}'   # tagged automatically
curl -s -X PUT $B/api/questions/1/answer/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' -d '{"text":"Only the basics of Dart are needed."}'       # 201, then 200 on replace
curl -s $B/api/lectures/KBTU26/summary/
curl -s $B/api/lectures/KBTU26/export/ -o KBTU26.md

# 5. token lifecycle
curl -s -X POST $B/api/auth/refresh/ -H 'Content-Type: application/json' -d "{\"refresh\":\"$REFRESH\"}"   # new pair
curl -s -X POST $B/api/auth/refresh/ -H 'Content-Type: application/json' -d "{\"refresh\":\"$REFRESH\"}"   # 401: blacklisted
curl -s -X POST $B/api/auth/logout/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' -d '{"refresh":"<the new one>"}'
```
