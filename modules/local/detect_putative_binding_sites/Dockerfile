# modules/local/detect_putative_binding_sites/Dockerfile

FROM python:3.12-slim-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

COPY libs/lynceus-chem ./libs/lynceus-chem
COPY libs/protein-conformational-ensemble ./libs/protein-conformational-ensemble
COPY modules/local/detect_putative_binding_sites ./modules/local/detect_putative_binding_sites
COPY modules/local/physiochemical_filter ./modules/local/physiochemical_filter
COPY modules/local/sample_candidates ./modules/local/sample_candidates
COPY modules/local/docking_prep ./modules/local/docking_prep

ENV UV_PROJECT_ENVIRONMENT=/opt/venv

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package detect-putative-binding-sites

FROM python:3.12-slim-trixie AS final

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    curl \
    openjdk-25-jdk \
    && rm -rf /var/lib/apt/lists/*

ENV P2RANK_HOME=/opt/p2rank_2.5.1
ENV PATH="${P2RANK_HOME}:/opt/venv/bin:${PATH}"

RUN curl -sSL https://github.com/rdk/p2rank/releases/download/2.5.1/p2rank_2.5.1.tar.gz | tar -xz -C /opt

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

COPY modules/local/detect_putative_binding_sites/src ./src

ENTRYPOINT []
