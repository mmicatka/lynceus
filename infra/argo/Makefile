# infra/argo/Makefile

include .env
export

CHART_VERSION := 2.0.11
APP_VERSION := v4.1.4
CSI_CHART_VERSION := 2.8.0

ARGO_NAMESPACE ?= argo
WORKFLOW_NAMESPACE ?= workflows
CSI_NAMESPACE ?= kube-system
CSI_SECRET_NAME ?= aws-secret
CSI_RELEASE ?= aws-mountpoint-s3-csi-driver

S3_SCHEME := $(if $(filter true,$(S3_INSECURE)),http,https)
S3_ENDPOINT_URL := $(S3_SCHEME)://$(S3_ENDPOINT)

.PHONY: all bootstrap rbac require-region csi-driver volumes deploy clean

all: bootstrap rbac csi-driver volumes deploy

bootstrap:
	@chmod +x scripts/bootstrap.sh
	./scripts/bootstrap.sh

rbac:
	kubectl apply -f resources/rbac.yaml

require-region:
	@test -n "$(S3_REGION)" || { echo 'S3_REGION is not set in .env' >&2; exit 1; }

csi-driver:
	helm repo add aws-mountpoint-s3-csi-driver https://awslabs.github.io/mountpoint-s3-csi-driver
	helm repo update aws-mountpoint-s3-csi-driver
	helm upgrade --install $(CSI_RELEASE) aws-mountpoint-s3-csi-driver/aws-mountpoint-s3-csi-driver \
		--namespace $(CSI_NAMESPACE) \
		--version $(CSI_CHART_VERSION) \
		--set awsAccessSecret.name=$(CSI_SECRET_NAME) \
		--wait

volumes: require-region
	sed -e 's|REPLACE_ME_S3_ENDPOINT_URL|$(S3_ENDPOINT_URL)|g' \
		-e 's|REPLACE_ME_S3_BUCKET|$(S3_BUCKET)|g' \
		-e 's|REPLACE_ME_S3_REGION|$(S3_REGION)|g' \
		resources/pv.yaml | kubectl apply -f -
	kubectl apply -f resources/pvc.yaml

deploy: require-region
	helm repo add argo https://argoproj.github.io/argo-helm
	helm repo update argo
	helm upgrade --install argo-workflows argo/argo-workflows \
		--namespace $(ARGO_NAMESPACE) \
		--version $(CHART_VERSION) \
		-f resources/values.yaml \
		--set images.tag=$(APP_VERSION) \
		--set artifactRepository.s3.endpoint=$(S3_ENDPOINT) \
		--set artifactRepository.s3.bucket=$(S3_BUCKET) \
		--set artifactRepository.s3.region=$(S3_REGION) \
		--set artifactRepository.s3.insecure=$(S3_INSECURE)

clean:
	helm uninstall argo-workflows --namespace $(ARGO_NAMESPACE) || true
	kubectl delete -f resources/pvc.yaml --ignore-not-found || true
	kubectl delete pv lynceus-bucket-pv --ignore-not-found || true
	helm uninstall $(CSI_RELEASE) --namespace $(CSI_NAMESPACE) || true
	kubectl delete secret $(CSI_SECRET_NAME) --namespace $(CSI_NAMESPACE) --ignore-not-found || true
	kubectl delete namespace $(ARGO_NAMESPACE) $(WORKFLOW_NAMESPACE) || true
