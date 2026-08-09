#!/usr/bin/env bash
set -euo pipefail

kubectl exec -it deploy/nf-driver -n lynceus -- \
  bash -c "cd /workspace/lynceus && nextflow run main.nf -profile k8s-onprem $*"
