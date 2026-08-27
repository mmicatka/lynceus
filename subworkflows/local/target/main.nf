// subworkflows/target/main.nf

include { GENERATE_MANIFEST } from '../../../modules/local/generate_manifest'

workflow TARGET {
  take:
  ensemble

  main:
  GENERATE_MANIFEST(ensemble)
}
