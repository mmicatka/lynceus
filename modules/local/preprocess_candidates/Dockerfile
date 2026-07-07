# Build locally: docker build -t lynceus/preprocess-candidates:0.1.0 .

FROM python:3.14-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN uv pip install --system --no-cache .

ENTRYPOINT []
