# Lynceus pipeline
#
# Each `run-<env>` target wraps `nextflow run main.nf -params-file conf/examples/<env>.yaml`
# so environment-specific parameters never need to be typed by hand or
# forgotten on the command line.

.PHONY: build build-lynceus-chem build-detect-putative-binding-sites run-test run-dev clean reset

build:
	$(MAKE) build-lynceus-chem
	$(MAKE) build-detect-putative-binding-sites

build-lynceus-chem:
	docker build -t lynceus/lynceus-chem:0.1.0 libs/lynceus-chem

build-detect-putative-binding-sites:
	docker build -f modules/local/detect_putative_binding_sites/Dockerfile -t lynceus/detect-putative-binding-sites:0.1.0 .

# Dev environment: loads conf/examples/dev.yaml
run-dev:
	nextflow run main.nf -resume -params-file conf/examples/dev.yaml

clean:
	rm -rf work/
	rm -rf .nextflow*
	rm -f nextflow.log*

reset: clean
	rm -rf results/*
