# Human Cutout

Human Cutout is a local full-stack application for binary human segmentation and simple image composition. A user creates an account, receives 30 demo credits, removes a person from a photo, or places that cutout over another image.

The project uses PyTorch for the trained U-Net, FastAPI and PostgreSQL for the application, and React + TypeScript for the browser UI.

## What it does

- **Person segmentation** costs one credit and produces a binary mask, transparent cutout, and overlay.
- **Combine with another image** costs two credits. The browser editor lets the user drag the cutout, use the mouse wheel to resize it, mirror it, and download the final PNG.
- New accounts receive 30 credits. **Recharge** is deliberately a local-demo reset back to 30.
- A dark/light green theme is available from the page header.

## Composition editor

![Human Cutout composition editor](docs/composition.png)

The editor preview above is captured from the local frontend. The extracted person can be dragged, resized with the mouse wheel, mirrored, and downloaded as a PNG.

## Data contract

The source dataset must have matching `images/` and `masks/` filenames. The preparation command validates all pairs, excludes collages by reading only those two directories, converts source images to RGB, converts masks to grayscale binary (`0` background, `255` person), and writes 256×256 files. Images use bilinear interpolation; masks use nearest-neighbour interpolation.

The deterministic split is 80% train / 10% validation / 10% test: for 2,667 pairs, that is 2,133 / 266 / 268 samples.

## Why 256×256

The four downsampling stages require dimensions divisible by 16. 256×256 preserves substantially more detail than 128 while allowing a U-Net with 32 base channels, deep dropout, batch size 8, and mixed precision within the target 6 GB RTX 4050 budget. If a local CUDA measurement reports out-of-memory, lower `batch_size` in `configs/train.json` to 4 before reducing resolution.

## Commands

Use a supported Python version (3.10–3.14) with an NVIDIA-enabled PyTorch installation.

If PyTorch is already installed in an activated conda environment such as `torch`, use that environment's `python`; the scripts support direct execution and do not require installing this package first.

```bash
# Option A: existing conda environment with PyTorch
conda activate torch
python scripts/prepare_data.py --raw-root ../archive/supervisely_person_clean_2667_img --output-root data/processed
python scripts/train.py
python scripts/verify_checkpoint.py

# Option B: a new virtual environment
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python scripts/prepare_data.py --raw-root ../archive/supervisely_person_clean_2667_img --output-root data/processed
.venv/bin/python scripts/train.py
.venv/bin/python scripts/verify_checkpoint.py
```

The last command must succeed before any inference API is added. A real trained checkpoint is saved to `backend/weights/model.pth` only when validation Dice improves.

## Run locally

Use three terminals from the repository root. Docker is used only for PostgreSQL; FastAPI uses the local `torch` conda environment and loads the local checkpoint.

**Terminal 1 — PostgreSQL**

```bash
newgrp docker  # needed only until a new login session includes the docker group
cd ~/UNET/UNET/human-segmentation-platform
docker compose up db -d
docker compose ps
```

Wait until `db` reports `healthy`. Do not run `docker compose down --volumes` unless you want to delete local accounts, credits, and metadata.

**Terminal 2 — API**

```bash
cd ~/UNET/UNET/human-segmentation-platform
conda activate torch
python -m pip install -e '.[dev]'
python -m uvicorn backend.app.main:app --reload
```

Verify it in a fourth shell if desired:

```bash
curl http://127.0.0.1:8000/api/health
```

The expected result contains `"status":"ok"`, with both the model and database ready.

**Terminal 3 — browser UI**

```bash
cd ~/UNET/UNET/human-segmentation-platform/frontend
npm install
VITE_USE_POLLING=true npm run dev
```

Open the exact local URL printed by Vite, normally `http://localhost:5173`. Polling avoids Linux `ENOSPC` file-watcher limits; it is not a memory leak.

## Trained model baseline

The initial U-Net has been trained on the prepared 2,667-pair dataset split (2,133 train / 266 validation / 268 test). The best checkpoint is intentionally excluded from Git and is available locally at `backend/weights/model.pth`.

| Field | Result |
| --- | --- |
| Architecture | Four-level U-Net, 32 base channels, deep dropout `0.2` |
| Input | Normalized RGB 256×256 |
| Best epoch | 38 of 40 |
| Best validation Dice | 0.9229 |
| Validation loss at best epoch | 0.2336 |
| Fresh-process checkpoint test | Passed: output shape `(1, 1, 256, 256)` |

The final epoch did not replace this artifact: its validation Dice was 0.9171. Checkpoints are selected strictly by validation Dice, not by the last epoch.

## API

The checkpoint verifier has passed for the initial trained model. Start PostgreSQL and the API with environment values suitable for your machine. The API needs `SEGMENTATION_DATABASE_URL`, `SEGMENTATION_CHECKPOINT_PATH`, and a non-default `SEGMENTATION_RATE_LIMIT_SALT` in production.

```bash
export SEGMENTATION_DATABASE_URL='postgresql+psycopg://segmentation:segmentation@localhost:5432/segmentation'
export SEGMENTATION_RATE_LIMIT_SALT='replace-this-with-a-secret'
cd /home/atharva/UNET/UNET/human-segmentation-platform
python -m uvicorn backend.app.main:app --reload
```

Or use Docker Compose (copy `.env.example` to `.env` and set its rate-limit salt first):

```bash
docker compose up --build
curl http://localhost:8000/api/health
```

The Compose configuration mounts the locally trained checkpoint read-only and keeps PostgreSQL and generated uploads in Docker volumes. It requests an NVIDIA GPU; remove `gpus: all` from [docker-compose.yml](docker-compose.yml) if NVIDIA Container Toolkit is not installed.

Key endpoints are `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/recharge`, `POST /api/predictions`, and `POST /api/compositions`. The application uses cookie sessions, per-user credits, and a small secondary IP-based usage guard. See [architecture.md](docs/architecture.md).

## Frontend

The React + TypeScript client in [frontend/](/home/atharva/UNET/UNET/human-segmentation-platform/frontend) provides person-image upload, original/mask/overlay comparison, API error states, and prediction history. It reads `/api/capabilities`, so new operations can be added to the backend without changing its app structure.

With the API running at `http://127.0.0.1:8000`, start the Vite development server in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` and `/media` to the local API. For a separately deployed backend, set `VITE_API_BASE_URL` before building:

```bash
VITE_API_BASE_URL=https://api.example.com npm run build
```

If Vite reports `ENOSPC` file-watcher errors on Linux, use polling instead of inotify:

```bash
VITE_USE_POLLING=true npm run dev
```

## Accounts and credits

The local application uses email/password accounts with PBKDF2 password hashing and an HTTP-only session cookie. Every new account receives 30 credits. Person segmentation costs one credit; creating an editable composition costs two credits. The top bar displays the balance and its **Recharge** button resets the current local/demo account to 30 credits.

After pulling these changes, update the active conda environment and restart FastAPI so the local database gets its non-destructive schema update:

```bash
conda activate torch
python -m pip install -e '.[dev]'
python -m uvicorn backend.app.main:app --reload
```

For a composition, choose **Combine with another image**, upload the person photo and background, then drag the cutout in the canvas. Scroll over the canvas to resize it and use **Mirror** to flip it. The download creates a PNG from the exact client-side placement.

## Future direction: more realistic background replacement

The current composition is intentionally a fast, editable raw paste. Its limitations are visible: hard edges, no ground contact shadow, mismatched lighting, and a person that can look sharper or cleaner than the background.

The next improvement will use only OpenCV and NumPy—no new ML model. It will add [compositing.py](backend/app/services/compositing.py) with:

```python
composite(person_rgb, mask, background_rgb, x, y, scale, params=None) -> composite_rgb
```

The planned, explainable pipeline is: feather and slightly erode the mask; place/clip the person; match LAB mean and standard deviation to the nearby background; draw a soft contact shadow before the person; match blur and film grain; then alpha composite entirely in float32. The API will accept background upload, placement, scale, and optional edge/shadow/color/grain controls. The future UI will add sliders and a raw-paste-versus-refined comparison toggle.

This work must proceed one testable step at a time, with confirmation after each step. It will include OpenCV/NumPy-only tests, a comparison-image script, and [COMPOSITING.md](docs/COMPOSITING.md) before it is considered complete.

## Replacing or retraining the model

The API reads its input dimensions, normalization, resize strategy, output threshold, architecture identifier, and U-Net channel/dropout configuration from the checkpoint. Therefore a compatible U-Net retrained at 512×512 (or another size divisible by 16) needs no frontend or API code change: replace `backend/weights/model.pth`, run the verifier, then restart the API.

Newly trained checkpoints use metadata format v2. The existing trained v1 checkpoint remains supported. A fundamentally new network architecture needs a small explicit model factory registration in [checkpoints.py](src/segmentation/checkpoints.py); the backend deliberately rejects unknown architecture IDs rather than loading incompatible weights unsafely.

For the design and implementation story, read [WALKTHROUGH.md](WALKTHROUGH.md).
