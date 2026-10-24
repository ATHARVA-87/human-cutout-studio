# Human Cutout

[![CI](https://github.com/ATHARVA-87/human-cutout-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/ATHARVA-87/human-cutout-studio/actions/workflows/ci.yml)

A U-Net trained from scratch to separate people from the background, served as a full-stack web app. Sign up, cut a person out of a photo, or place them into another picture with a drag-and-resize editor.

**Live demo:** _link added after deployment_. It runs on a free server that sleeps when idle, so the first visit can take about a minute to wake up.

![Composition editor](docs/composition.png)

## Features

- **Person segmentation** (1 credit): binary mask, transparent cutout with soft edges, and a tinted overlay.
- **Combine with another image** (2 credits): the person is cropped, colour-matched to the new background, and placed in a canvas editor. Drag to move, scroll or use the slider to resize, mirror, and download a PNG. Half-body photos stay glued to the bottom edge; full-body ones get a soft contact shadow.
- **History**: a separate page lists your past cutouts and compositions (paginated). Open a result again, reopen a composition in the editor, or delete it.
- **Accounts and credits**: 30 free credits on sign-up, demo recharge when you run out, one active session per account, and a rate limit of 10 jobs per 30 minutes per user.
- **Privacy by design**: a full [Privacy Notice](frontend/src/pages/PrivacyPage.tsx) page. Uploads and results are **deleted automatically after 5 days**. Self-service account deletion. One strictly necessary cookie, no trackers, self-hosted fonts.
- **Security**: salted password hashing, hashed session tokens, HTTP-only cookies, a limit of 5 failed sign-ins per 15 minutes, per-user access checks, a strict Content Security Policy and security headers, and a request ID on every response.
- **Design**: a cutting-mat workspace, the editor's "marching ants" selection and the transparency checkerboard as the visual language. Light and dark theme, a show/hide password toggle, drag-and-drop uploads, and full keyboard support including the editor.

## Model results

| | |
| --- | --- |
| Architecture | 4-level U-Net, 32 base channels, BatchNorm, dropout in the deepest layers (7.8 M parameters) |
| Data | 2,667 image/mask pairs at 256×256, split 2,133 train / 266 validation / 268 test |
| Loss | Binary cross-entropy + soft Dice |
| Best validation Dice | **0.9229** (epoch 38 of 40) |
| Test Dice | **0.9259** on the 268 untouched test images, measured once |
| Serving | Exported to ONNX (31 MB), matches PyTorch to within 1e-5 |

## How it works

```text
Browser (React + TypeScript)
   │  same origin: cookies just work, no CORS
   ▼
FastAPI ──► rate limit (token bucket) ──► credits ──► U-Net on ONNX Runtime ──► realism steps
   │                                                                        (crop, colour match)
   ├── PostgreSQL: users, sessions, credit ledger, rate-limit buckets, login attempts, history
   ├── uploads/: generated images, served at /media/...
   └── retention job (startup + hourly): deletes data older than 5 days
```

Training happens offline in PyTorch on a GPU (`src/segmentation`, `scripts/`). The best checkpoint is exported to `model.onnx`, and the web server only needs that file.

## Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| Model | PyTorch U-Net, trained from scratch | Shows the full ML loop: data preparation, training, validation, a held-out test |
| Serving | ONNX Runtime | About half the memory of PyTorch, so it fits a free 512 MB server |
| API | FastAPI (Python) | Typed request validation, async I/O, automatic docs at `/docs` |
| Database | PostgreSQL + SQLAlchemy | Transactions, constraints and row locks keep credits and rate limits correct under concurrency |
| Frontend | React + TypeScript (Vite) | Component UI with type safety; the editor is a plain `<canvas>` |
| Packaging | Docker (multi-stage) | One image runs the same way locally and in production |
| CI/CD | GitHub Actions + Render Blueprint | Tests (with a real Postgres) on every push; deploys only when CI passes |
| Hosting | Render (app) · Neon (Postgres) · Hugging Face Hub (model file) | All free tiers, no credit card |

## Run it locally

You need Docker. To develop, you also need Python 3.11+ and Node 22.

**Option A: everything in Docker (same as production)**

```bash
cp .env.example .env
docker compose up --build
```

Open http://localhost:8000. If `backend/weights/model.onnx` is missing, the build downloads it from `MODEL_URL`.

**Option B: development with hot reload**

```bash
cp .env.example .env
docker compose up db -d                       # PostgreSQL only
python -m pip install -e '.[dev]'             # once (use a venv or conda env)
python -m uvicorn backend.app.main:app --reload
# second terminal
cd frontend && npm install && npm run dev     # open the URL Vite prints (http://localhost:5173)
```

Vite forwards `/api` and `/media` to FastAPI on port 8000. If Linux reports `ENOSPC` file-watcher errors, run `VITE_USE_POLLING=true npm run dev`.

**Tests:** `python -m pytest`. The API tests need the Docker database running and use a separate `segmentation_test` database.

## Train, evaluate and export the model

```bash
python -m pip install -e '.[train]'
python scripts/prepare_data.py --raw-root <dataset with images/ and masks/> --output-root data/processed
python scripts/train.py                     # saves backend/weights/model.pth when validation Dice improves
python scripts/verify_checkpoint.py         # reloads it in a fresh process
python scripts/evaluate_test_split.py       # one-time test-set Dice
python scripts/export_onnx.py               # writes backend/weights/model.onnx for the server
```

Hyperparameters live in [configs/train.json](configs/train.json). The checkpoint stores its own architecture and preprocessing settings, and the ONNX file carries them too, so the server never hard-codes the input size.

## Database admin (owner only)

There is no admin web page. These commands need the database connection string, so only the person holding it can run them:

```bash
python scripts/db_admin.py stats     # size and row counts (keep an eye on the free-tier storage limit)
python scripts/db_admin.py cleanup   # run the 5-day retention job now (it also runs automatically every hour)
python scripts/db_admin.py reset     # deletes ALL users and history; asks you to type the database name

# production: pass the Neon connection string for this one command
SEGMENTATION_DATABASE_URL='postgresql+psycopg://…neon.tech/neondb?sslmode=require' python scripts/db_admin.py stats
```

## API

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/api/auth/register` · `/api/auth/login` | JSON `{email, password}`; sets an HTTP-only session cookie |
| POST | `/api/auth/logout` | 204 |
| GET | `/api/auth/me` | current email, credits and retention period |
| POST | `/api/auth/recharge` | +30 credits, only when below 2 |
| DELETE | `/api/auth/account` | JSON `{password}`; deletes the account and all its data |
| POST | `/api/predictions` | multipart `image` (JPG/PNG ≤ 10 MB); 1 credit |
| GET | `/api/predictions?limit=&offset=` · `/api/predictions/{id}` | your history only, newest first |
| DELETE | `/api/predictions/{id}` | removes the row and its files |
| POST | `/api/compositions` | multipart `person_image` + `background_image`; 2 credits |
| GET / DELETE | `/api/compositions`, `/api/compositions/{id}` | same pattern as predictions |
| GET | `/api/health` | model and database status (503 when degraded) |

Errors: 401 (not signed in), 402 (not enough credits), 403 (wrong password on account deletion), 404 (not found or not yours), 415 (not JPG/PNG), 429 (rate limited or too many failed sign-ins, with `Retry-After`). Interactive docs: `/docs`.

## Project structure

```text
backend/app/
  api/          HTTP routes (auth, predictions, compositions, health)
  services/     auth, credits, rate_limit, jobs, inference (ONNX), realism, storage, retention
  db/           SQLAlchemy models and session
  core/         settings from environment variables, request middleware (request ID, logs, security headers)
frontend/src/   React app: App.tsx + router.ts, pages/ (Create, History, Privacy), components/ (Composer, …)
src/segmentation/  U-Net, dataset, training loop, checkpoint contract, ONNX export
scripts/        prepare_data, train, verify_checkpoint, evaluate_test_split, export_onnx, db_admin
tests/          unit tests + API tests against real PostgreSQL
Dockerfile · docker-compose.yml · render.yaml · .github/workflows/ci.yml
```

## Deployment

`render.yaml` describes the production service: the Docker image runs on Render's free plan, the database is a free Neon PostgreSQL, and `model.onnx` is downloaded from the Hugging Face Hub during the build. Pushing to `main` runs CI, and Render deploys only when CI passes. Step-by-step instructions are in [WALKTHROUGH.md](WALKTHROUGH.md#13-deploying-for-free-step-by-step).

## Limitations

- The model works at 256×256, so fine details like hair are approximate. It sometimes includes bright background patches, such as sky near the horizon.
- The realism steps are classic image processing. They do not fix perspective or the direction of light.
- On the free plan, generated images are stored on the server's temporary disk and disappear when it restarts. History entries are kept in PostgreSQL until the 5-day retention job deletes them.

## Dataset

Trained on a cleaned subset (2,667 image/mask pairs) of the Supervisely Person dataset. Check the original dataset's license before reusing its images.
