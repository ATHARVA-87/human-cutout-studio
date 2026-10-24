# One image = the whole app. Used by `docker compose up` locally AND by Render in production.

# ---------- Stage 1: build the React app into static files ----------
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Python API that also serves those static files ----------
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 MALLOC_ARENA_MAX=2

# Exact, locked versions of every server dependency (no PyTorch: the model runs on ONNX Runtime).
# Installing from the lock file means every build gets the same packages.
COPY requirements.lock ./
RUN pip install -r requirements.lock
COPY pyproject.toml alembic.ini ./
COPY src ./src
RUN pip install --no-deps .
COPY backend ./backend

# The exported model is not in Git. Use a local backend/weights/model.onnx if it exists,
# otherwise download it from MODEL_URL (the Hugging Face Hub link; Render passes it as a build arg).
ARG MODEL_URL=""
RUN if [ ! -f backend/weights/model.onnx ]; then \
      if [ -z "$MODEL_URL" ]; then echo "Need backend/weights/model.onnx or a MODEL_URL build argument" && exit 1; fi; \
      python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" "$MODEL_URL" backend/weights/model.onnx; \
    fi

COPY --from=frontend /frontend/dist ./frontend/dist

# Run as an unprivileged user, not root: if the app were ever compromised, the attacker could not
# modify the system or the app's own code. Only uploads/ is writable.
RUN useradd --create-home --uid 10001 app && mkdir -p uploads && chown app:app uploads
USER app

EXPOSE 8000
# $PORT: Render chooses the port (8000 locally).
# --proxy-headers: behind Render's proxy, take the real client IP from X-Forwarded-For (used by the
# per-IP limits). FORWARDED_ALLOW_IPS says which proxies to trust: only Render sets it to "*".
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
