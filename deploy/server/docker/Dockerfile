# Single-process image: builds the SvelteKit static client, then bakes it
# into the FastAPI server image so one container serves both the SPA and the
# API from the same origin (no CORS, one port, one process to deploy).
#
# Build from the REPO ROOT (context needs both client/ and server/):
#   docker build -f deploy/server/docker/Dockerfile -t directstream .
#
# Run:
#   docker run -p 8000:8000 --env-file server/.env directstream

# ---- Stage 1: build the static client -------------------------------------
FROM node:22-alpine AS client-build
WORKDIR /client

COPY client/package.json client/package-lock.json ./
RUN npm ci

COPY client/ ./

# Leave empty for single-process deploy (same-origin, relative API calls).
# Only set this if you're baking a client meant to call a DIFFERENT origin.
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ---- Stage 2: Python runtime ------------------------------------------------
FROM python:3.12-slim AS server
WORKDIR /app

# ffmpeg: needed by yt-dlp for merging/remuxing formats and audio extraction.
# curl: used by the container HEALTHCHECK below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./
COPY --from=client-build /client/build ./client_build

RUN useradd --create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV CLIENT_DIR=/app/client_build \
    HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# run.py reads HOST/PORT/WORKERS from the environment (see server/app/config.py).
CMD ["python", "run.py"]
