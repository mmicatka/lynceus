# Lynceus pipeline

REGISTRY ?= registry.nebula.lan:5000
NAMESPACE ?= lynceus
VERSION ?= 0.1.0
IMAGE_PREFIX := $(REGISTRY)/$(NAMESPACE)

.PHONY: build push build-* clean reset lint

build-generate-conformers:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/generate_conformers/Dockerfile -t $(IMAGE_PREFIX)/generate-conformers:$(VERSION) .

build-generate-features:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/generate_features/Dockerfile -t $(IMAGE_PREFIX)/generate-features:$(VERSION) .

build-surrogate-model:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/surrogate_model/Dockerfile -t $(IMAGE_PREFIX)/surrogate-model:$(VERSION) .

build-rebalance-candidates:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/rebalance_candidates/Dockerfile -t $(IMAGE_PREFIX)/rebalance-candidates:$(VERSION) .

build-detect-binding-sites:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/detect_binding_sites/Dockerfile -t $(IMAGE_PREFIX)/detect-binding-sites:$(VERSION) .

build-docking-run:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f modules/local/docking_run/Dockerfile -t $(IMAGE_PREFIX)/docking-run:$(VERSION) .

lint:
	ruff check --fix .
