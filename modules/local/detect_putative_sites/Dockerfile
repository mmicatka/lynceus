# modules/local/detect_putative_sites/Dockerfile

FROM python:3.12-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

COPY libs/protein-conformational-ensemble ./libs/protein-conformational-ensemble
COPY libs/lynceus-chem ./libs/lynceus-chem


COPY modules/local/detect_putative_sites ./modules/local/detect_putative_sites

WORKDIR /app/modules/local/detect_putative_sites

RUN uv pip install --system .

ENTRYPOINT []
