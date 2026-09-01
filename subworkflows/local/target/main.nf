// subworkflows/target/main.nf

include { DETECT_BINDING_SITES } from '../../../modules/local/detect_binding_sites'

workflow TARGET {
  take:
  ch_ensemble // tuple(val(ensemble_id), path(ensemble_path))

  main:
  DETECT_BINDING_SITES(ch_ensemble)

  ch_target_surfaces = DETECT_BINDING_SITES.out.sites
    .join(ch_ensemble)
    .map { _ensemble_id, sites_path, ensemble_path -> tuple(ensemble_path, sites_path) }

  emit:
  target_surfaces = ch_target_surfaces // tuple(path(ensemble_path), path(sites_path))
}
