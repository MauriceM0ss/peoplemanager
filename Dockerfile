# Pinned by digest for reproducible builds. This is python:3.12-slim as of
# 2026-07-03; rebuild with a fresh digest periodically to pick up security
# updates (docker pull python:3.12-slim && docker inspect --format
# '{{index .RepoDigests 0}}' python:3.12-slim).
FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

WORKDIR /app

COPY requirements.txt .

# Install build deps, compile Python packages, then swap to runtime-only lib
RUN apt-get update && \
    apt-get install -y --no-install-recommends libsqlcipher-dev gcc && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y libsqlcipher-dev gcc && \
    apt-get install -y --no-install-recommends libsqlcipher1 && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY . .

# /data is a named volume that persists the database and config
VOLUME ["/data"]

EXPOSE 8080

ENV DB_PATH=/data/people.db

# Liveness probe — hits the unauthenticated /healthz endpoint using the stdlib
# (no curl in the slim image). Marks the container unhealthy if Flask stops
# responding.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status==200 else 1)"]

CMD ["python", "app.py"]
