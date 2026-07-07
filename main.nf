#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

include { LYNCEUS } from './workflows/lynceus'

workflow {
  LYNCEUS()
}
