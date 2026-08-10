# Lynceus pipeline
#
# Each `run-<env>` target wraps `nextflow run main.nf -params-file conf/examples/<env>.yaml`

# --- Configuration Variables ---
REGISTRY ?= registry.nebula.lan:8080
NAMESPACE ?= lynceus
VERSION ?= 0.1.0
IMAGE_PREFIX := $(REGISTRY)/$(NAMESPACE)
K8S_NAMESPACE ?= lynceus
NF_DRIVER_DEPLOYMENT ?= nf-driver

.PHONY: build push build-* push-* run-dev run-k8s driver-exec driver-restart clean reset lint

build: build-lynceus-chem build-detect-putative-binding-sites build-protein-conformational-ensemble build-docking-prep build-sample-candidates build-physiochemical-filter build-docking-run-cpu build-docking-run-gpu build-nf-driver

build-lynceus-chem:
	docker buildx build --platform linux/amd64,linux/arm64 --push -t $(IMAGE_PREFIX)/lynceus-chem:$(VERSION) libs/lynceus-chem

build-protein-conformational-ensemble:
	docker buildx build --platform linux/amd64,linux/arm64 --push -t $(IMAGE_PREFIX)/protein-conformational-ensemble:$(VERSION) libs/protein-conformational-ensemble

build-detect-putative-binding-sites:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/detect_putative_binding_sites/Dockerfile -t $(IMAGE_PREFIX)/detect-putative-binding-sites:$(VERSION) .

build-docking-prep:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/docking_prep/Dockerfile -t $(IMAGE_PREFIX)/docking-prep:$(VERSION) .

build-sample-candidates:
	docker buildx build --platform linux/amd64,linux/arm64 --push -t $(IMAGE_PREFIX)/sample-candidates:$(VERSION) modules/local/sample_candidates

build-physiochemical-filter:
	docker buildx build --platform linux/amd64,linux/arm64 --push -t $(IMAGE_PREFIX)/physiochemical-filter:$(VERSION) modules/local/physiochemical_filter

build-docking-run-cpu:
	docker buildx build --platform linux/amd64,linux/arm64 --push --target cpu -t $(IMAGE_PREFIX)/docking-run:cpu-$(VERSION) modules/local/docking_run

build-docking-run-gpu:
	docker buildx build --platform linux/amd64 --push --target gpu -t $(IMAGE_PREFIX)/docking-run:gpu-$(VERSION) modules/local/docking_run

build-nf-driver:
	docker buildx build --platform linux/amd64 --push -f driver.Dockerfile -t $(IMAGE_PREFIX)/nf-driver:$(VERSION) .

# --- Utilities ---
# Dev environment: loads conf/examples/dev.yaml
run-dev:
	nextflow run main.nf -resume -params-file conf/examples/dev.yaml

# k8s-onprem environment: runs in-cluster via the nf-driver pod
# Usage: make run-k8s ARGS="-params-file conf/examples/dev.yaml -resume"
run-k8s:
	kubectl exec -it deploy/$(NF_DRIVER_DEPLOYMENT) -n $(K8S_NAMESPACE) -- \
		bash -c "cd /app/lynceus && nextflow run main.nf -profile k8s-onprem $(ARGS)"

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
