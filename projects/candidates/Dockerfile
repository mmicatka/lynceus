# projects/candidates/Dockerfile

FROM python:3.14-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.14-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

COPY libs/lynceus-core ./libs/lynceus-core

COPY projects/candidates ./projects/candidates
WORKDIR /app/projects/candidates

RUN uv pip install --system .

ENTRYPOINT []
