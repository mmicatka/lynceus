# modules/local/detect_putative_binding_sites/Dockerfile

FROM python:3.12-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    curl \
    openjdk-25-jdk \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

ENV P2RANK_VERSION=2.5.1
ENV P2RANK_HOME=/opt/p2rank_${P2RANK_VERSION}
ENV PATH="${P2RANK_HOME}:${PATH}"

RUN curl -fsSL "https://github.com/rdk/p2rank/releases/download/${P2RANK_VERSION}/p2rank_${P2RANK_VERSION}.tar.gz" \
    | tar -xz -C /opt

WORKDIR /app

COPY pyproject.toml uv.lock ./

COPY libs/lynceus-chem ./libs/lynceus-chem

COPY modules/local/detect_putative_binding_sites ./modules/local/detect_putative_binding_sites

WORKDIR /app/modules/local/detect_putative_binding_sites

RUN uv pip install --system .

ENTRYPOINT []
