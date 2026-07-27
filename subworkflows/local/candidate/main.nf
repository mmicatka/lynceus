// subworkflows/candidate/main.nf

include { RETRIEVE_CANDIDATES } from '../../../modules/local/retrieve_candidates'
include { PREPROCESS_CANDIDATES } from '../../../modules/local/preprocess_candidates'
include { PHYSIOCHEMICAL_FILTER } from '../../../modules/local/physiochemical_filter'
include { DOCKING_PREP_CANDIDATE } from '../../../modules/local/docking_prep'

workflow CANDIDATE {
  take:
  uri_list // path: file containing one download URI per line, or [] to skip
  local_path // path: local candidate file(s)/glob, or [] to skip
  config // path: YAML physiochemical filter configuration
  batch_size // val:  max rows per output parquet partition

  main:
  ch_versions = channel.empty()

  if (local_path) {
    // Bypass aria2c entirely — use already-staged local candidate file(s)
    ch_candidates = channel.fromPath(local_path, checkIfExists: true)
    ch_download_log = channel.empty()
  }
  else {
    RETRIEVE_CANDIDATES(uri_list)
    ch_versions = ch_versions.mix(RETRIEVE_CANDIDATES.out.versions)

    ch_candidates = RETRIEVE_CANDIDATES.out.candidates
    ch_download_log = RETRIEVE_CANDIDATES.out.log
  }

  // Fan out: one PREPROCESS_CANDIDATES process per downloaded .smi.gz file.
  ch_smi_gz = ch_candidates
    .flatten()
    .filter { file -> file.name.endsWith('.smi.gz') }

  PREPROCESS_CANDIDATES(ch_smi_gz)
  ch_versions = ch_versions.mix(PREPROCESS_CANDIDATES.out.versions)
  ch_all_parquet = PREPROCESS_CANDIDATES.out.parquet.collect()

  PHYSIOCHEMICAL_FILTER(ch_all_parquet, config, batch_size)
  ch_versions = ch_versions.mix(PHYSIOCHEMICAL_FILTER.out.versions)

  DOCKING_PREP_CANDIDATE(ch_all_parquet)
  ch_versions = ch_versions.mix(DOCKING_PREP_CANDIDATE.out.versions)

  emit:
  filtered_parquets = PHYSIOCHEMICAL_FILTER.out.parquet.collect() // path: filtered + repartitioned parquet
  filter_report = PHYSIOCHEMICAL_FILTER.out.report // path: filter_report.json
  versions = ch_versions // channel: [ versions.yml ]
}
