# modules/local/docking_prep/Dockerfile

FROM python:3.12-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    gcc \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

COPY libs/protein-conformational-ensemble ./libs/protein-conformational-ensemble

COPY modules/local/docking_prep ./modules/local/docking_prep

WORKDIR /app/modules/local/docking_prep

RUN uv pip install --system .

ENTRYPOINT []
