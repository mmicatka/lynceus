# Lynceus pipeline
#
# Each `run-<env>` target wraps `nextflow run main.nf -params-file conf/examples/<env>.yaml`
# so environment-specific parameters never need to be typed by hand or
# forgotten on the command line.

.PHONY: build build-preprocess build-physiochemical-filter run-test run-dev clean

build: build-preprocess build-physiochemical-filter

build-preprocess:
	docker build -t lynceus/preprocess-candidates:0.1.0 modules/local/preprocess_candidates

build-physiochemical-filter:
	docker build -t lynceus/physiochemical-filter:0.1.0 modules/local/physiochemical_filter

## Dev environment: loads conf/examples/dev.yaml
run-dev:
	nextflow run main.nf -resume -params-file conf/examples/dev.yaml

clean:
	rm -rf work/
	rm -rf .nextflow*
	rm -f nextflow.log*
