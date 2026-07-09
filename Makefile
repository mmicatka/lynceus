# Lynceus pipeline
#
# Each `run-<env>` target wraps `nextflow run main.nf -params-file conf/examples/<env>.yaml`
# so environment-specific parameters never need to be typed by hand or
# forgotten on the command line.

.PHONY: build build-preprocessrun-test run-dev

## Build the two locally-built module images (run once, or after any
## change to their pyproject.toml/Dockerfile/src).
build: build-preprocess

build-preprocess:
	docker build -t lynceus/preprocess-candidates:0.1.0 modules/local/preprocess_candidates

build-filter:
	docker build -t lynceus/physiochem-filter:0.1.0 modules/local/physiochem_filter

## Smoke test: tiny built-in URI list, no params file needed.
run-test:
	nextflow run main.nf -profile test

## Dev environment: loads conf/examples/dev.yaml
run-dev:
	nextflow run main.nf -params-file conf/examples/dev.yaml
