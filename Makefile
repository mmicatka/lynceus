# Makefile

REGISTRY ?= registry.nebula.lan:5000
IMAGE_PREFIX := $(REGISTRY)/lynceus

TEMPLATES_CONFIG ?= conf/templates.yaml
CANDIDATES_CONFIG ?= conf/candidates.yaml

SCREEN_CONFIG ?= conf/screen/ptprb-10m-100k-valid-5-rounds-5k.yaml

NAMESPACE ?= workflows
VERSION ?= 0.1.0

WORKFLOWS ?= load-candidates-workflow sample-candidates-workflow preprocess-candidates-workflow targets-workflow surrogate-workflow
OUT_DIR ?= workflows/manifests

PRIORITY ?=
POD_PRIORITY_CLASS ?=

.PHONY: build push build-* clean lint lint-python lint-argo generate generate-workflows submit-workflows run logs

build-candidates:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f projects/candidates/Dockerfile -t $(IMAGE_PREFIX)/candidates:$(VERSION) .

build-targets:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f projects/targets/Dockerfile -t $(IMAGE_PREFIX)/targets:$(VERSION) .

build-lynceus-dock:
	docker buildx build --platform linux/amd64 --push -f projects/lynceus-dock/Dockerfile -t $(IMAGE_PREFIX)/lynceus-dock:$(VERSION) .

build-surrogate-model:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f projects/surrogate-model/Dockerfile -t $(IMAGE_PREFIX)/surrogate-model:$(VERSION) .

setup-argo:
	$(MAKE) -C infra/argo all WORKFLOW_NAMESPACE=$(NAMESPACE)

generate-workflows:
	@echo "Generating workflows: $(WORKFLOWS)..."
	generate-workflows \
		$(foreach wf,$(WORKFLOWS),-w $(wf)) \
		-o $(OUT_DIR) \
		-t $(TEMPLATES_CONFIG) \
		-c $(CANDIDATES_CONFIG) \
		-s $(SCREEN_CONFIG) \
		$(if $(PRIORITY),--priority $(PRIORITY)) \
		$(if $(POD_PRIORITY_CLASS),--pod-priority-class $(POD_PRIORITY_CLASS))

submit-workflows: generate-workflows
	@echo "Submitting workflows: $(WORKFLOWS) to namespace $(NAMESPACE)..."
	@for wf in $(WORKFLOWS); do \
		argo submit -n $(NAMESPACE) $(OUT_DIR)/$$wf.yaml; \
	done

generate: generate-workflows

lint-argo: generate
	@echo "Linting generated manifests..."
	@for wf in $(WORKFLOWS); do \
		argo lint $(OUT_DIR)/$$wf.yaml; \
	done

lint-python:
	ruff check --fix .

lint-yaml:
	yamllint .

lint: lint-python lint-argo lint-yaml


clean:
	rm -f $(OUT_DIR)/*.yaml
	@echo "Cleaned up generated YAML files."
