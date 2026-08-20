FROM python:3.12-slim-trixie

ARG TARGETARCH
ARG NEXTFLOW_VERSION=26.04.6
ARG KUBECTL_VERSION=v1.31.0

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
  openjdk-25-jdk  \
  curl \
  ca-certificates \
  git \
  make \
  && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /usr/local/bin/kubectl \
  "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
  && chmod +x /usr/local/bin/kubectl

RUN curl -fsSL https://github.com/nextflow-io/nextflow/releases/download/v${NEXTFLOW_VERSION}/nextflow \
  -o /usr/local/bin/nextflow \
  && chmod +x /usr/local/bin/nextflow \
  && NXF_HOME=/opt/nextflow nextflow -version


ENV NXF_HOME=/opt/nextflow
ENV PATH="/usr/local/bin:${PATH}"

WORKDIR /app/lynceus

COPY . .

CMD ["sleep", "infinity"]
