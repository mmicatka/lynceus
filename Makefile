# Lynceus pipeline
#
# Each `run-<env>` target wraps `nextflow run main.nf -params-file conf/examples/<env>.yaml`
# so environment-specific parameters never need to be typed by hand or
# forgotten on the command line.

.PHONY: build build-lynceus-chem build-detect-putative-binding-sites build-protein-conformational-ensemble build-docking-prep build-sample-candidates build-physiochemical-filter run-dev clean reset

build:
	$(MAKE) build-lynceus-chem
	$(MAKE) build-protein-conformational-ensemble
	$(MAKE) build-detect-putative-binding-sites
	$(MAKE) build-docking-prep
	$(MAKE) build-sample-candidates
	$(MAKE) build-physiochemical-filter

build-lynceus-chem:
	docker build -t lynceus/lynceus-chem:0.1.0 libs/lynceus-chem

build-protein-conformational-ensemble:
	docker build -t lynceus/protein-conformational-ensemble:0.1.0 libs/protein-conformational-ensemble

build-detect-putative-binding-sites:
	docker build -f modules/local/detect_putative_binding_sites/Dockerfile -t lynceus/detect-putative-binding-sites:0.1.0 .

build-docking-prep:
	docker build -f modules/local/docking_prep/Dockerfile -t lynceus/docking-prep:0.1.0 .

build-sample-candidates:
	docker build -t lynceus/sample-candidates:0.1.0 modules/local/sample_candidates

build-physiochemical-filter:
	docker build -t lynceus/physiochemical-filter:0.1.0 modules/local/physiochemical_filter

# Dev environment: loads conf/examples/dev.yaml
run-dev:
	nextflow run main.nf -resume -params-file conf/examples/dev.yaml

clean:
	rm -rf work/
	rm -rf .nextflow*
	rm -f nextflow.log*

reset: clean
	rm -rf results/*

lint:
	ruff check --fix .
