// subworkflows/targets/main.nf

include { DETECT_BINDING_SITES } from '../../../modules/local/detect_binding_sites'

workflow TARGETS {
  take:
  config

  main:
  def bucket = config.bucket
  def valid_ensembles = []

  config.ensembles.each { ensemble_id ->
    def ensemble_root = "${config.ensemble_prefix}/${ensemble_id}"
    def validation_uri = bucket ? "s3://${bucket}/${ensemble_root}" : ensemble_root

    if (!file("${validation_uri}/manifest.json").exists()) {
      log.warn("Skipping ensemble ${ensemble_id}: manifest.json not found for ${validation_uri}")
    }
    else if (files("${validation_uri}/members/*").isEmpty()) {
      log.warn("Skipping ensemble ${ensemble_id}: no member structure files found for ${validation_uri}/members")
    }
    else {
      valid_ensembles << tuple(ensemble_id, ensemble_root)
    }
  }

  ch_valid_ensemble = channel.fromList(valid_ensembles)

  DETECT_BINDING_SITES(ch_valid_ensemble)

  ch_target_surfaces = DETECT_BINDING_SITES.out.sites
    .join(ch_valid_ensemble)
    .map { _ensemble_id, sites_path, ensemble_root ->
      tuple(ensemble_root, sites_path)
    }

  ch_done = DETECT_BINDING_SITES.out.sites
    .collect()
    .map { true }
    .first()

  emit:
  done = ch_done
  target_surfaces = ch_target_surfaces // tuple(val(ensemble_root), val(sites_path))
  ensemble = ch_valid_ensemble // tuple(val(ensemble_id), val(ensemble_root))
}
