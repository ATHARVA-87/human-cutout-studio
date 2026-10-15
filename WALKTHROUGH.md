# Project walkthrough

This is a revision guide for explaining the project from data preparation to the local browser application.

## 1. Why a new repository

The old U-Net project was inspected only as an architectural reference. It was removed after the new repository was created so this project has one clear source of truth: [src/](./src) for ML code, [backend/](./backend) for the service, and [frontend/](./frontend) for the UI.

## 2. Data decisions

The archive was verified rather than assumed: it contains 2,667 matching image/mask filenames; source image sizes vary widely; masks encode background as `0` and person as `255`. Collages are ignored because preparation reads only `images/` and `masks/`.

Every pair is converted to RGB plus binary grayscale mask and resized to 256×256. Images use bilinear resize; masks use nearest-neighbour resize so class labels do not become fractional. The seeded split is 2,133 training / 266 validation / 268 test samples.

256×256 is divisible by 16, which fits the four U-Net downsampling levels. It is a practical starting resolution for the RTX 4050’s 6 GB VRAM with batch size 8 and mixed precision.

## 3. Model and checkpoint

The model keeps classic U-Net encoder-decoder skip connections. It adds configurable `Dropout2d` only in deeper layers, where regularisation helps without erasing shallow edge information.

The trained checkpoint is selected by validation Dice, not by the final epoch. Training reached its best validation Dice of 0.9229 at epoch 38. [model.pth](backend/weights/model.pth) is ignored by Git, but it includes weights, model configuration, preprocessing, threshold, checkpoint version, epoch, and score.

This metadata is important: the API reconstructs the compatible U-Net and input preprocessing from the checkpoint instead of hard-coding 256×256. A retrained compatible U-Net can therefore replace the weight file after verification and API restart.

## 4. Backend design

FastAPI starts the model once and records prediction metadata in PostgreSQL through SQLAlchemy. Uploaded images, masks, transparent cutouts, and overlays are local media artifacts, not Git files.

Passwords use PBKDF2-HMAC-SHA256 with a unique random salt. Browser sessions use random opaque tokens stored as hashes in the database and sent through HTTP-only cookies. The browser never receives a password hash or session secret.

Credits are stored on the user and changed using a conditional database update (`credits >= cost`). This prevents two simultaneous requests from spending the same credit balance. Each change also creates an immutable credit-transaction record.

The small startup schema migration exists only to keep this local evolving database compatible. A production project should move this work to Alembic migrations.

## 5. Frontend design

The landing UI starts with two explicit choices: segmentation or composition. It reads account state, displays credits, provides recharge for the demo, and keeps the mode/theme in simple React state or browser storage.

The editor uses a canvas for responsiveness. The cutout moves on pointer drag, scales with wheel events, and mirrors via canvas transform. This gives immediate feedback and makes the final PNG download match what the user sees. The server still owns authentication, credit charging, segmentation, and persisted input artifacts.

## 6. Problems encountered and resolutions

| Problem | Resolution |
| --- | --- |
| Source images have different dimensions | Validate matching pairs, then resize image and mask consistently during preparation. |
| Initial environment lacked Python packages | Use the existing `torch` conda environment with CUDA-enabled PyTorch. |
| Direct `scripts/train.py` could not import `segmentation` | Add the project `src/` directory to direct-script imports while retaining packaging support. |
| Old and new projects occupied disk | Remove the confirmed legacy implementation, failed environment, and caches while retaining raw/processed data and trained weights. |
| Docker daemon permission denied | Add the account to the Docker group and create a new shell/login session. |
| Local FastAPI could not reach PostgreSQL | Publish Compose PostgreSQL on `localhost:5432`, then restart FastAPI after the database is healthy. |
| Vite exhausted inotify watchers (`ENOSPC`) | Use Vite polling with `VITE_USE_POLLING=true`. |

## 7. What comes next

The priority is a realistic but explainable compositing service. It will use plain OpenCV + NumPy for soft edges, LAB color transfer, contact shadows, blur/grain matching, and float32 alpha blending. It remains intentionally separate from the U-Net: segmentation decides *what is person*; compositing decides *how it should look in a new scene*.
