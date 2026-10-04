# Makefile

REGISTRY ?= registry.nebula.lan:5000
IMAGE_PREFIX := $(REGISTRY)/lynceus

NAMESPACE ?= workflows
VERSION ?= 0.1.0


WORKFLOWS ?= echo
OUT_DIR ?= workflows/manifests

.PHONY: build push build-* clean lint lint-python lint-argo generate generate-workflows submit run logs

build-candidates:
	docker buildx build --platform linux/amd64,linux/arm64 --push -f projects/candidates/Dockerfile -t $(IMAGE_PREFIX)/candidates:$(VERSION) .

setup-argo:
	$(MAKE) -C infra/argo all WORKFLOW_NAMESPACE=$(NAMESPACE)

generate-workflows:
	@echo "Generating workflows: $(WORKFLOWS)..."
	generate-workflows $(foreach wf,$(WORKFLOWS),-w $(wf)) -o $(OUT_DIR)

# Alias to satisfy the lint-argo dependency
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

submit: generate
	@echo "Submitting workflows: $(WORKFLOWS) to namespace $(NAMESPACE)..."
	@for wf in $(WORKFLOWS); do \
		argo submit -n $(NAMESPACE) $(OUT_DIR)/$$wf.yaml; \
	done

clean:
	rm -f $(OUT_DIR)/*.yaml
	@echo "Cleaned up generated YAML files."
