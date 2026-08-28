# modules/local/preprocess_candidates/Dockerfile

FROM python:3.12-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

COPY libs/lynceus-utils ./libs/lynceus-utils
COPY libs/protein-conformational-ensemble ./libs/protein-conformational-ensemble

COPY modules/local/preprocess_candidates ./modules/local/preprocess_candidates

WORKDIR /app/modules/local/preprocess_candidates

RUN uv pip install --system .

RUN python -c "import duckdb; duckdb.execute('INSTALL httpfs')"

ENTRYPOINT []
