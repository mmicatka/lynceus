# Base Stage
FROM ubuntu:24.04 AS base
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    aria2 git curl ca-certificates build-essential cmake wget \
    software-properties-common sudo \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && curl -s https://get.nextflow.io | bash \
    && rm -rf /var/lib/apt/lists/*
