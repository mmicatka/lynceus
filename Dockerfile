# Dockerfile

# Base Stage
FROM ubuntu:24.04 AS base
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    aria2 \
    git \
    curl ca-certificates build-essential cmake wget \
    software-properties-common sudo unzip zip openjdk-25-jdk  \
    swig libboost-all-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -s https://get.nextflow.io | bash \
    && mv nextflow /usr/local/bin/ \
    && chmod +x /usr/local/bin/nextflow

ENV P2RANK_HOME=/opt/p2rank_2.5.1
ENV PATH="${P2RANK_HOME}:${PATH}"

RUN curl -sSL https://github.com/rdk/p2rank/releases/download/2.5.1/p2rank_2.5.1.tar.gz | tar -xz -C /opt

ARG USERNAME=appuser
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd --gid ${USER_GID} ${USERNAME} || groupmod -n ${USERNAME} $(getent group ${USER_GID} | cut -d: -f1) \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME} || usermod -l ${USERNAME} -m -d /home/${USERNAME} $(getent passwd ${USER_UID} | cut -d: -f1) \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME}

# install uv as user
USER ${USERNAME}
RUN curl -LsSf https://astral.sh/uv/install.sh | bash

USER root

# Dev CPU
FROM base AS dev-cpu
RUN apt-get update \
    && apt-get install -y tree graphviz zsh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspaces/lynceus
USER appuser

RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

# GPU Base
FROM base AS base-gpu
RUN apt-get update && apt-get install -y gnupg wget \
    && wget -qO /tmp/cuda-keyring.deb https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb \
    && dpkg -i /tmp/cuda-keyring.deb \
    && apt-get update \
    && apt-get install -y \
    cuda-compiler-12-6 \
    cuda-libraries-dev-12-6 \
    cuda-runtime-12-6 \
    cuda-cudart-dev-12-6 \
    cudnn9-cuda-12 \
    cuda-nvtx-12-6 \
    && rm -rf /var/lib/apt/lists/* /tmp/cuda-keyring.deb

ENV CUDA_PATH=/usr/local/cuda
ENV PATH="/usr/local/cuda/bin:${PATH}"
ENV LD_LIBRARY_PATH="/usr/local/cuda/lib64:/usr/lib/wsl/lib"
ENV GPU_INCLUDE_PATH=/usr/local/cuda/include
ENV GPU_LIBRARY_PATH=/usr/local/cuda/lib64

# GPU Dev
FROM base-gpu AS dev-gpu

RUN apt-get update \
    && apt-get install -y tree graphviz zsh \
    && rm -rf /var/lib/apt/lists/*

RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

WORKDIR /workspaces/lynceus
USER appuser
