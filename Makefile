# Lynceus pipeline
#
# Each `run-<env>` target wraps `nextflow run main.nf -params-file conf/examples/<env>.yaml`

# --- Configuration Variables ---
REGISTRY ?= registry.nebula.lan:5000
NAMESPACE ?= lynceus
VERSION ?= 0.1.0
IMAGE_PREFIX := $(REGISTRY)/$(NAMESPACE)
K8S_NAMESPACE ?= lynceus
NF_DRIVER_DEPLOYMENT ?= nf-driver

.PHONY: build push build-* run-dev run-k8s driver-exec driver-restart clean reset lint

build: build-preprocess-candidates build-physiochemical-filter build-rebalance-candidates build-sample-candidates build-detect-binding-sites build-prepare-ensemble build-docking-run-gpu build-nf-driver

build-preprocess-candidates:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/preprocess_candidates/Dockerfile -t $(IMAGE_PREFIX)/preprocess-candidates:$(VERSION) .

build-physiochemical-filter:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/physiochemical_filter/Dockerfile -t $(IMAGE_PREFIX)/physiochemical-filter:$(VERSION) .

build-rebalance-candidates:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/rebalance_candidates/Dockerfile -t $(IMAGE_PREFIX)/rebalance-candidates:$(VERSION) .

build-sample-candidates:
	docker buildx build --platform linux/amd64,linux/arm64 --push -t $(IMAGE_PREFIX)/sample-candidates:$(VERSION) modules/local/sample_candidates

build-detect-binding-sites:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/detect_binding_sites/Dockerfile -t $(IMAGE_PREFIX)/detect-binding-sites:$(VERSION) .

build-prepare-ensemble:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/prepare_ensemble/Dockerfile -t $(IMAGE_PREFIX)/docking-prep:$(VERSION) .

build-docking-run-gpu:
	docker buildx build --platform linux/amd64 --push --target gpu -t $(IMAGE_PREFIX)/docking-run:gpu-$(VERSION) modules/local/docking_run

build-nf-driver:
	docker buildx build --platform linux/amd64 --push -f driver.Dockerfile -t $(IMAGE_PREFIX)/nf-driver:$(VERSION) .

# --- Utilities ---
# Dev environment: loads conf/examples/dev.yaml
run-dev:
	nextflow run main.nf -resume -params-file conf/examples/dev.yaml

run-k8s-local:
	nextflow run main.nf -resume -profile k8s-onprem -params-file conf/params.yaml

# k8s-onprem environment: runs in-cluster via the nf-driver pod
run-k8s:
	kubectl exec -it deploy/$(NF_DRIVER_DEPLOYMENT) -n $(K8S_NAMESPACE) -- \
		bash -c "cd /app/lynceus && nextflow run main.nf -profile k8s-onprem -resume"

# Drop into a shell on the driver pod
driver-exec:
	kubectl exec -it deploy/$(NF_DRIVER_DEPLOYMENT) -n $(K8S_NAMESPACE) -- bash

# Force a fresh pull of the latest nf-driver image (after build-nf-driver + push)
driver-restart:
	kubectl rollout restart deployment/$(NF_DRIVER_DEPLOYMENT) -n $(K8S_NAMESPACE)
	kubectl rollout status deployment/$(NF_DRIVER_DEPLOYMENT) -n $(K8S_NAMESPACE)

clean:
	rm -rf work/
	rm -rf .nextflow*
	rm -f nextflow.log*
	rm -rf null/

reset: clean
	rm -rf results/*

lint:
	ruff check --fix .
