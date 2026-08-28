// subworkflows/target/main.nf

include { DETECT_BINDING_SITES } from '../../../modules/local/detect_binding_sites'
include { PREPARE_ENSEMBLE } from '../../../modules/local/prepare_ensemble'

workflow TARGET {
  take:
  ensemble_path

  main:
  DETECT_BINDING_SITES(ensemble_path)
  PREPARE_ENSEMBLE(ensemble_path)

  ch_target_surfaces = DETECT_BINDING_SITES.out.sites
    .join(PREPARE_ENSEMBLE.out.prepped)
    .map { ensemble_id, sites, prepped -> tuple(ensemble_id, sites, prepped) }

  emit:
  target_surfaces = ch_target_surfaces
}
