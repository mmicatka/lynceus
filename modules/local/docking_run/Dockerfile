# modules/local/docking_run/Dockerfile

FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS vina-gpu-builder

ARG VINA_GPU_REPO=https://github.com/DeltaGroupNJUPT/Vina-GPU-2.1.git
ARG VINA_GPU_REF=main
ARG GPU_PLATFORM=Nvidia
ARG BOOST_VERSION=1.83.0

RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  git \
  wget \
  ocl-icd-opencl-dev \
  ocl-icd-libopencl1 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/boost-src
RUN BOOST_UNDERSCORE=$(echo "${BOOST_VERSION}" | tr '.' '_') \
  && wget -q "https://archives.boost.io/release/${BOOST_VERSION}/source/boost_${BOOST_UNDERSCORE}.tar.gz" \
  && tar -xzf "boost_${BOOST_UNDERSCORE}.tar.gz" \
  && mv "boost_${BOOST_UNDERSCORE}" /opt/boost \
  && rm -rf /opt/boost-src

WORKDIR /opt/vina-gpu
RUN git clone --depth 1 --branch "${VINA_GPU_REF}" "${VINA_GPU_REPO}" .

RUN make \
  BOOST_LIB_PATH=/opt/boost \
  BOOST_INCLUDE_PATH=/opt/boost \
  OPENCL_INCLUDE_PATH=/usr/include \
  OPENCL_LIB_PATH=/usr/lib/x86_64-linux-gnu \
  GPU_PLATFORM="${GPU_PLATFORM}" \
  && test -x ./Vina-GPU

RUN mkdir -p /opt/vina-gpu-dist \
  && cp ./Vina-GPU /opt/vina-gpu-dist/ \
  && find . -maxdepth 1 -iname "*.txt" -exec cp {} /opt/vina-gpu-dist/ \;

FROM python:3.12-slim-trixie AS cpu

RUN apt-get update && apt-get install -y --no-install-recommends \
  procps \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN uv pip install --system .

ENTRYPOINT []

FROM python:3.12-slim-trixie AS gpu

RUN apt-get update && apt-get install -y --no-install-recommends \
  procps \
  ocl-icd-libopencl1 \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN uv pip install --system .

COPY --from=vina-gpu-builder /opt/vina-gpu-dist/ /opt/vina-gpu/
ENV PATH="/opt/vina-gpu:${PATH}"
ENV LYNCEUS_VINA_GPU_BIN=/opt/vina-gpu/Vina-GPU
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

ENTRYPOINT []
