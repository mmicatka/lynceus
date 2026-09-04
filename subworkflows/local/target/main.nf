// subworkflows/target/main.nf

include { DETECT_BINDING_SITES } from '../../../modules/local/detect_binding_sites'

workflow TARGET {
  take:
  ch_ensemble // tuple(val(ensemble_id), path(ensemble_files))

  main:
  DETECT_BINDING_SITES(ch_ensemble)

  ch_target_surfaces = DETECT_BINDING_SITES.out.sites
    .join(ch_ensemble)
    .map { _ensemble_id, sites_path, ensemble_files -> tuple(ensemble_files, sites_path) }

  emit:
  target_surfaces = ch_target_surfaces // tuple(path(ensemble_dir), path(sites_path))
}
