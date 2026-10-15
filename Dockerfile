# CUDA-enabled base image: inference uses the GPU automatically when Docker is
# launched with NVIDIA GPU access; it safely falls back to CPU otherwise.
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY backend ./backend
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
