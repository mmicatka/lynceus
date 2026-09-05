// subworkflows/target/main.nf

include { DETECT_BINDING_SITES } from '../../../modules/local/detect_binding_sites'

workflow TARGET {
  take:
  ch_ensemble // tuple(val(ensemble_id), path(manifest), path(members))

  main:
  DETECT_BINDING_SITES(ch_ensemble)

  ch_target_surfaces = DETECT_BINDING_SITES.out.sites
    .join(ch_ensemble)
    .map { _ensemble_id, sites_path, manifest, members -> tuple(manifest, members, sites_path) }

  emit:
  target_surfaces = ch_target_surfaces // tuple(path(manifest), path(members), path(sites_path))
  ensemble = ch_ensemble // tuple(val(ensemble_id), path(manifest), path(members))
}
