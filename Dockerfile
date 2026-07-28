# Two stages, because the two layers have genuinely different needs: the client
# needs Node only to build and never to run, and shipping a Node toolchain into
# the runtime image would roughly triple it for no benefit.
#
# Deliberately portable rather than tied to one host. It runs the same way on
# Render, Fly, Railway, Cloud Run or a plain VM, which matters more than shaving
# a layer — the alternative is a host-specific build script that has to be
# rewritten the first time the hosting decision changes.

# ----------------------------------------------------------- stage 1: client
FROM node:22-alpine AS web

WORKDIR /build
# Manifests first so the dependency layer caches independently of source edits.
COPY web/package.json web/package-lock.json* ./
RUN npm ci || npm install

COPY web/ ./
RUN npm run build


# ---------------------------------------------------------- stage 2: runtime
FROM python:3.12-slim

# Bytecode files and stdout buffering are both pure liability in a container:
# the first bloats the image, the second hides logs when a process dies.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e ".[api]"

COPY api/ ./api/
# The built SPA, into the path api/main.py looks for. If this is missing the app
# still serves /api correctly and simply has no front end — a mounted-last
# catch-all, not a hard dependency.
COPY --from=web /build/dist ./web/dist

# Non-root: nothing here needs write access at runtime.
RUN useradd --create-home --shell /bin/false app && chown -R app:app /app
USER app

EXPOSE 8000

# $PORT is injected by most hosts and defaults to 8000 for a local run. Shell
# form so the variable actually expands.
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
