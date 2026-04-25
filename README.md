# ClipGenius AI

> **Repurpose long-form videos into viral short-form content. Auto-distribute across YouTube Shorts and Instagram Reels.**

ClipGenius AI is a production-grade SaaS platform that takes a YouTube URL or uploaded video, transcribes it with Whisper, finds the most viral moments using NLP + audio engagement detection, generates 5–10 vertical (9:16) short clips with face-aware reframing and dynamic burned-in captions, optionally dubs them into multiple languages, generates per-platform metadata, and schedules / posts them to YouTube Shorts and Instagram Reels.

---

## Architecture

```
┌──────────────┐     ┌─────────────────────────────┐     ┌──────────────┐
│  Next.js UI  │ ──► │   FastAPI (REST + OAuth)    │ ──► │  Postgres    │
│   (Vercel)   │     │       (Render Web)          │     │ (Render DB)  │
└──────────────┘     └──────────────┬──────────────┘     └──────────────┘
                                    │ enqueue
                                    ▼
                            ┌──────────────┐
                            │ Redis broker │
                            │  (Render)    │
                            └──────┬───────┘
                                   │
                  ┌────────────────┴────────────────┐
                  ▼                                 ▼
        ┌─────────────────┐              ┌─────────────────────┐
        │ Celery worker   │              │ Celery beat         │
        │ video pipeline: │              │ scheduler:          │
        │  yt-dlp ▶ Whisper│             │  publish_due_posts  │
        │  segment ▶ ffmpeg│             │  refresh_analytics  │
        │  reframe ▶ caps  │             └─────────────────────┘
        │  dub  ▶ S3       │
        └─────────────────┘
                  │
                  ▼
        ┌──────────────────┐
        │  AWS S3 storage  │ ──► YouTube Data API v3 / Meta Graph API
        └──────────────────┘
```

## Tech stack

| Layer       | Tech                                                                |
|-------------|---------------------------------------------------------------------|
| Frontend    | Next.js 14 (App Router), TypeScript, Tailwind, SWR                  |
| Backend     | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2                     |
| Worker      | Celery 5 + Redis                                                    |
| AI          | OpenAI Whisper (transcription), GPT-4o-mini (translation/captions), OpenAI TTS |
| Video       | yt-dlp, FFmpeg, OpenCV (face tracking)                              |
| Storage     | AWS S3 (with local-disk fallback for dev)                           |
| Auth        | JWT (email/password) + OAuth for YouTube & Meta                     |
| Database    | PostgreSQL 16                                                       |
| Hosting     | Render (API + worker + beat + Redis + Postgres) · Vercel (frontend) |

## Project layout

```
backend/                FastAPI service + Celery worker (Dockerised)
  app/
    config.py           env-driven settings
    database.py         SQLAlchemy engine + sync session
    models/             User, Video, Clip, ScheduledPost, OAuthAccount
    schemas/            Pydantic request/response shapes
    auth/               JWT, password hashing, FastAPI deps
    services/
      storage.py        S3 (with local fallback)
      openai_client.py  Whisper + chat + TTS
      downloader.py     yt-dlp wrapper
      segmenter.py      heuristic + LLM clip selection
      video_processor.py FFmpeg + OpenCV pipeline
      captioner.py      Per-platform metadata generator
      youtube.py        YouTube Data API
      instagram.py      Meta Graph API (Reels publish)
    routers/            REST endpoints
    tasks/              Celery app + tasks (video + posting)
    main.py             FastAPI entrypoint
  Dockerfile
  pyproject.toml + requirements.txt
  tests/

frontend/               Next.js 14 app
  app/                  pages (landing, auth, dashboard, projects, schedule, settings)
  components/           AuthGuard, Sidebar, ClipCard, Logo
  lib/                  api client, types, helpers
  package.json + tsconfig

render.yaml             Render Blueprint (API + worker + beat + redis + postgres)
docker-compose.yml      Local dev stack
```

## How it works

1. **Submit project** — user pastes a YouTube URL or uploads a video, picks output languages and target platforms.
2. **Download / fetch** — yt-dlp grabs ≤1080p MP4 (or the upload is pulled from S3).
3. **Transcribe** — Whisper produces segment-level timestamps.
4. **Find viral moments** — `segmenter.select_viral_moments` builds candidate windows over the transcript, scores each on:
   - **audio energy** (per-second RMS via ffmpeg)
   - **viral keywords** (curated lexicon)
   - **pause patterns** (gaps preceding strong moments)
   then asks GPT to rank them and write a hook + title for each.
5. **Render clips** — for each pick: cut → 9:16 reframe with **face-aware center crop** (OpenCV Haar cascade smoothed across time) → build per-clip ASS subtitles with **uppercase 2-line captions and yellow keyword highlights** → burn captions → upload to S3.
6. **Dub** (optional) — translate transcript via GPT, synthesise voice via OpenAI TTS, replace the audio track.
7. **Generate metadata** — GPT writes per-platform titles / descriptions / hashtags.
8. **Schedule + publish** — user picks a time and platform from the dashboard. Celery beat polls the schedule and dispatches publish tasks; YouTube uploads via the Data API v3, Instagram publishes Reels via the Meta Graph API.
9. **Analytics** — every 30 min Celery beat refreshes view/like counts for posts published in the last 30 days.

## Local development

Prereqs: Docker, Docker Compose, an OpenAI API key.

```bash
cp backend/.env.example backend/.env   # fill in OPENAI_API_KEY (others optional)
cp frontend/.env.example frontend/.env

docker compose up --build
```

Then open <http://localhost:3000>. The API is at <http://localhost:8000>, OpenAPI docs at `/docs`.

For native dev (without Docker):

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Worker (separate shell)
celery -A app.worker worker --loglevel=info
celery -A app.worker beat --loglevel=info

# Frontend (separate shell)
cd frontend
npm install
npm run dev
```

## Deployment

### Backend on Render

1. Push this repo to GitHub.
2. In Render, choose **New > Blueprint** and select the repo. Render reads `render.yaml` and provisions:
   - `clipgenius-api` (web service)
   - `clipgenius-worker` and `clipgenius-beat` (workers)
   - `clipgenius-redis` (Redis)
   - `clipgenius-db` (Postgres)
3. Set the `sync: false` env vars in the dashboard:
   - `OPENAI_API_KEY`, `AWS_*`, `YOUTUBE_*`, `META_*`
   - `FRONTEND_URL` (your Vercel URL), `BACKEND_URL` (Render service URL)

### Frontend on Vercel

1. Import the repo into Vercel.
2. Set **Root Directory** to `frontend`.
3. Add env var `NEXT_PUBLIC_API_URL` pointing to your Render API URL.
4. Deploy.

### OAuth redirect URIs

Set the following redirect URIs in each provider:

- **YouTube (Google Cloud Console)**: `${BACKEND_URL}/api/v1/integrations/youtube/callback`
- **Meta (Facebook for Developers)**: `${BACKEND_URL}/api/v1/integrations/instagram/callback`

## API surface (highlights)

| Method | Path                                       | Description                            |
|--------|--------------------------------------------|----------------------------------------|
| POST   | `/api/v1/auth/signup` / `/auth/login`      | Create account / sign in (JWT)         |
| GET    | `/api/v1/auth/me`                          | Current user                           |
| POST   | `/api/v1/videos`                           | New project from a URL                 |
| POST   | `/api/v1/videos/upload`                    | New project from an uploaded file      |
| GET    | `/api/v1/videos`                           | List projects                          |
| GET    | `/api/v1/videos/{id}`                      | Project detail                         |
| GET    | `/api/v1/clips/by-video/{id}`              | Clips for a project                    |
| PATCH  | `/api/v1/clips/{id}`                       | Edit clip metadata                     |
| POST   | `/api/v1/posts`                            | Schedule a post                        |
| GET    | `/api/v1/posts`                            | List scheduled posts                   |
| DELETE | `/api/v1/posts/{id}`                       | Cancel a scheduled post                |
| GET    | `/api/v1/integrations/{provider}/connect`  | Start OAuth                            |
| GET    | `/api/v1/integrations/{provider}/callback` | Finish OAuth                           |

Full OpenAPI / Swagger UI is auto-served at `${BACKEND_URL}/docs`.

## Honest tradeoffs in this MVP

- **Lip-sync** is intentionally not in scope — high-quality lip-sync (Wav2Lip / SadTalker) requires GPU
  inference and adds a lot of operational complexity. We dub the audio track only. Adding a lip-sync
  pass is a self-contained future-work module that consumes the dubbed audio + clip and outputs a new
  video.
- **Face tracking** uses an OpenCV Haar cascade with temporal smoothing — robust enough for talking-head
  content but not as accurate as a deep model. Swappable for MediaPipe / RetinaFace later.
- **Engagement detection** is a transparent heuristic (audio RMS + curated viral lexicon + pause
  detection) plus an LLM ranker. There is no proprietary "viral score" model.
- **Meta posting** requires a reviewed Meta App for `instagram_content_publish`. Until reviewed, only
  IG Business / Creator accounts added as test users in the Meta App can be posted to.
- **YouTube OAuth** apps in test mode work for ~100 users until verified by Google.

## Compliance

- We respect YouTube's TOS by **only downloading content the user owns or has rights to** — the user is
  responsible for input. We do not strip watermarks or DRM.
- We respect Meta's TOS by publishing through the official Graph API endpoints and obeying scheduled
  publication semantics.
- All third-party tokens are stored encrypted-at-rest by the database; we never log access tokens.

## License

MIT — see `LICENSE`.
