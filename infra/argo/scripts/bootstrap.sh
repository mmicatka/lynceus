#!/usr/bin/env bash
# infra/argo/scripts/bootstrap.sh
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly ARGO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

log() {
  printf '==> %s\n' "$*" >&2
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

require_cmds() {
  local cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || die "missing required command: ${cmd}"
  done
}

require_vars() {
  local var
  for var in "$@"; do
    [[ -n "${!var:-}" ]] || die "missing required variable: ${var}"
  done
}

load_env() {
  local env_file="${ENV_FILE:-${ARGO_DIR}/.env}"
  [[ -f "$env_file" ]] || die "env file not found: ${env_file}"
  set -a
  source "$env_file"
  set +a
}

load_config() {
  ARGO_NAMESPACE="${ARGO_NAMESPACE:-argo}"
  WORKFLOW_NAMESPACE="${WORKFLOW_NAMESPACE:-workflows}"
  CSI_NAMESPACE="${CSI_NAMESPACE:-kube-system}"
  ARTIFACT_SECRET_NAME="${ARTIFACT_SECRET_NAME:-argo-artifacts-s3}"
  CSI_SECRET_NAME="${CSI_SECRET_NAME:-aws-secret}"
}

ensure_namespace() {
  local namespace="$1"
  kubectl get namespace "$namespace" >/dev/null 2>&1 || kubectl create namespace "$namespace"
}

apply_secret() {
  local name="$1" namespace="$2"
  shift 2

  local env_file="${WORK_DIR}/${namespace}.${name}.env"
  local pair
  : >"$env_file"
  for pair in "$@"; do
    printf '%s\n' "$pair" >>"$env_file"
  done

  kubectl create secret generic "$name" \
    --namespace "$namespace" \
    --from-env-file="$env_file" \
    --dry-run=client --output=yaml | kubectl apply --filename -
}

main() {
  require_cmds kubectl
  load_env
  load_config
  require_vars S3_ACCESS_KEY S3_SECRET_KEY

  log "Ensuring namespaces: ${ARGO_NAMESPACE}, ${WORKFLOW_NAMESPACE}, ${CSI_NAMESPACE}"
  ensure_namespace "$ARGO_NAMESPACE"
  ensure_namespace "$WORKFLOW_NAMESPACE"
  ensure_namespace "$CSI_NAMESPACE"

  log "Applying Argo artifact repository secret ${ARTIFACT_SECRET_NAME} in ${WORKFLOW_NAMESPACE}"
  apply_secret "$ARTIFACT_SECRET_NAME" "$WORKFLOW_NAMESPACE" \
    "accessKey=${S3_ACCESS_KEY}" \
    "secretKey=${S3_SECRET_KEY}"

  log "Applying Mountpoint CSI driver secret ${CSI_SECRET_NAME} in ${CSI_NAMESPACE}"
  apply_secret "$CSI_SECRET_NAME" "$CSI_NAMESPACE" \
    "key_id=${S3_ACCESS_KEY}" \
    "access_key=${S3_SECRET_KEY}"

  log "Bootstrap complete."
}

main "$@"
