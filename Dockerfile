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
# OMP_NUM_THREADS / MALLOC_ARENA_MAX keep PyTorch's memory use low on a small free server.
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 OMP_NUM_THREADS=1 MALLOC_ARENA_MAX=2

# CPU-only PyTorch: the free server has no GPU, and this build is far smaller than the CUDA one.
RUN pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml ./
COPY src ./src
RUN pip install .
COPY backend ./backend

# The trained weights are not in Git. Use a local backend/weights/model.pth if it exists,
# otherwise download it from MODEL_URL (the Hugging Face Hub link; Render passes it as a build arg).
ARG MODEL_URL=""
RUN if [ ! -f backend/weights/model.pth ]; then \
      if [ -z "$MODEL_URL" ]; then echo "Need backend/weights/model.pth or a MODEL_URL build argument" && exit 1; fi; \
      python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" "$MODEL_URL" backend/weights/model.pth; \
    fi

COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8000
# Render tells the app which port to use through $PORT; locally it defaults to 8000.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
