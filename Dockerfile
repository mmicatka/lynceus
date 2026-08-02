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

# NVIDIA Container Toolkit: required for the INNER Docker-in-Docker daemon
# to discover and pass GPUs through to containers it spawns (e.g. via
# `docker run --gpus all`). This is separate from and in addition to the
# CUDA userspace libraries installed above — those let code *inside this
# image* use the GPU directly; this lets the Docker daemon *running
# inside this image* expose the GPU to containers it launches. Missing
# this is exactly why `docker run --gpus all` previously failed here with
# "failed to discover GPU vendor from CDI: no known GPU vendor found",
# even though `nvidia-smi` worked fine directly in the devcontainer shell.
RUN curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
    && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list \
    && apt-get update \
    && apt-get install -y nvidia-container-toolkit \
    && rm -rf /var/lib/apt/lists/*

# `nvidia-ctk runtime configure` writes /etc/docker/daemon.json, which the
# inner dockerd reads at STARTUP — not at build time, since no daemon is
# running during `docker build`. This must run once the inner daemon is
# actually up (e.g. as part of the devcontainer's postCreateCommand /
# entrypoint / DinD startup script), not here as a RUN step. Documenting
# the required command here since it belongs conceptually with this
# install, even though it can't execute in this layer:
#
#   nvidia-ctk runtime configure --runtime=docker
#   systemctl restart docker   # or the equivalent dockerd restart for
#                               # however this image's DinD is supervised
#
# FIXME: wire the above into whatever starts dockerd in this devcontainer
# (entrypoint script / postCreateCommand) — it cannot live in this
# Dockerfile as a RUN instruction.

FROM base AS dev-cpu
ARG USERNAME=appuser
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd --gid ${USER_GID} ${USERNAME} || groupmod -n ${USERNAME} $(getent group ${USER_GID} | cut -d: -f1) \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME} || usermod -l ${USERNAME} -m -d /home/${USERNAME} $(getent passwd ${USER_UID} | cut -d: -f1) \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME}

RUN apt-get update \
    && apt-get install -y tree graphviz zsh \
    && rm -rf /var/lib/apt/lists/*

USER ${USERNAME}
RUN curl -LsSf https://astral.sh/uv/install.sh | bash
WORKDIR /workspaces/lynceus
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

FROM base-gpu AS dev-gpu
ARG USERNAME=appuser
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd --gid ${USER_GID} ${USERNAME} || groupmod -n ${USERNAME} $(getent group ${USER_GID} | cut -d: -f1) \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME} || usermod -l ${USERNAME} -m -d /home/${USERNAME} $(getent passwd ${USER_UID} | cut -d: -f1) \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME}

RUN apt-get update \
    && apt-get install -y tree graphviz zsh \
    && rm -rf /var/lib/apt/lists/*

USER ${USERNAME}
RUN curl -LsSf https://astral.sh/uv/install.sh | bash
WORKDIR /workspaces/lynceus
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
