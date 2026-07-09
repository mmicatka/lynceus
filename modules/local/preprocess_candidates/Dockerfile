# modules/local/preprocess_candidates/Dockerfile

FROM python:3.12-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
  procps \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

# Install dependencies into the system environment (no virtualenv needed
# inside a container that only ever runs this one thing).
RUN uv pip install --system --no-cache .

ENTRYPOINT []
