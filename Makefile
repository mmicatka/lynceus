# Lynceus pipeline
#
# Each `run-<env>` target wraps `nextflow run main.nf -params-file conf/examples/<env>.yaml`
# so environment-specific parameters never need to be typed by hand or
# forgotten on the command line.

.PHONY: build build-preprocess build-physiochemical-filter build-sample run-test run-dev clean reset

build: build-preprocess build-physiochemical-filter build-sample build-retrieve-pdb build-generate-manifest build-detect-putative-sites

build-preprocess:
	docker build -t lynceus/preprocess-candidates:0.1.0 modules/local/preprocess_candidates

build-physiochemical-filter:
	docker build -t lynceus/physiochemical-filter:0.1.0 modules/local/physiochemical_filter

build-sample:
	docker build -t lynceus/sample:0.1.0 modules/local/sample_candidates

build-retrieve-pdb:
	docker build -t lynceus/retrieve-pdb:0.1.0 modules/local/retrieve_pdb

build-generate-manifest:
	docker build -f modules/local/generate_manifest/Dockerfile -t lynceus/generate-manifest:0.1.0 .

build-detect-putative-sites:
	docker build -f modules/local/detect_putative_sites/Dockerfile -t lynceus/detect-putative-sites:0.1.0 .

# Dev environment: loads conf/examples/dev.yaml
run-dev:
	nextflow run main.nf -resume -params-file conf/examples/dev.yaml

clean:
	rm -rf work/
	rm -rf .nextflow*
	rm -f nextflow.log*

reset: clean
	rm -rf results/*
