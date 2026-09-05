# modules/local/docking_run/Dockerfile

FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04 AS gpu

RUN apt-get update && apt-get install -y --no-install-recommends \
  procps \
  git \
  ca-certificates \
  curl \
  python3.12 \
  python3.12-venv \
  bzip2 \
  libboost-all-dev \
  swig \
  g++ \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

ENV MAMBA_ROOT_PREFIX=/opt/micromamba
RUN curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest \
  | tar -xvj -C /usr/local/bin/ --strip-components=1 bin/micromamba

RUN micromamba create -y -n unidock -c conda-forge unidock \
  && micromamba clean --all --yes

ENV PATH=/opt/micromamba/envs/unidock/bin:$PATH

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN uv pip install --system .

ENTRYPOINT []
