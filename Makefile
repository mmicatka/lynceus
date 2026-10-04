# Lynceus pipeline

REGISTRY ?= registry.nebula.lan:5000
NAMESPACE ?= lynceus
VERSION ?= 0.1.0
IMAGE_PREFIX := $(REGISTRY)/$(NAMESPACE)

WORKFLOWS ?= echo
OUT_DIR ?= workflows/manifests

CLI_ARGS = $(foreach wf,$(WORKFLOWS),-w $(wf))

.PHONY: build push build-* clean lint lint-python lint-argo generate submit run logs

build-candidates:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f projects/candidates/Dockerfile -t $(IMAGE_PREFIX)/candidates:$(VERSION) .


generate-workflows:
	@echo "Generating workflows: $(WORKFLOWS)..."
	generate-workflows $(CLI_ARGS) -o $(OUT_DIR)

lint-argo: generate
	@echo "Linting generated manifests..."
	@for wf in $(WORKFLOWS); do \
		argo lint $(OUT_DIR)/$$wf.yaml; \
	done

submit: lint-argo
	@echo "Submitting workflows to namespace $(NAMESPACE)..."
	@for wf in $(WORKFLOWS); do \
		argo submit $(OUT_DIR)/$$wf.yaml -n $(NAMESPACE); \
	done

run: submit

logs:
	argo logs @latest -n $(NAMESPACE)

lint-python:
	ruff check --fix .

lint-yaml:
	yamllint .

lint: lint-python lint-argo lint-yaml

clean:
	rm -f $(OUT_DIR)/*.yaml
	@echo "Cleaned up generated YAML files."
