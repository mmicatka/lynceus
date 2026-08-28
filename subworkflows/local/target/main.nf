// subworkflows/target/main.nf

include { GENERATE_PCE_MANIFEST } from '../../../modules/local/generate_pce_manifest'

workflow TARGET {
  take:
  ensemble

  main:
  GENERATE_PCE_MANIFEST(ensemble)

  emit:
  done = GENERATE_PCE_MANIFEST.out.done
}
