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

# Server dependencies only (no PyTorch: the model runs on ONNX Runtime).
COPY pyproject.toml ./
COPY src ./src
RUN pip install .
COPY backend ./backend

# The exported model is not in Git. Use a local backend/weights/model.onnx if it exists,
# otherwise download it from MODEL_URL (the Hugging Face Hub link; Render passes it as a build arg).
ARG MODEL_URL=""
RUN if [ ! -f backend/weights/model.onnx ]; then \
      if [ -z "$MODEL_URL" ]; then echo "Need backend/weights/model.onnx or a MODEL_URL build argument" && exit 1; fi; \
      python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" "$MODEL_URL" backend/weights/model.onnx; \
    fi

COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8000
# Render tells the app which port to use through $PORT; locally it defaults to 8000.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
