// subworkflows/candidate/main.nf

include { RETRIEVE_CANDIDATES } from '../../modules/local/retrieve_candidates/main'
include { PREPROCESS_CANDIDATES } from '../../modules/local/preprocess_candidates/main'

workflow CANDIDATE {
  take:
  uri_list // path: file containing one download URI per line

  main:
  ch_versions = channel.empty()

  RETRIEVE_CANDIDATES(uri_list)
  ch_versions = ch_versions.mix(RETRIEVE_CANDIDATES.out.versions)

  // Fan out: one PREPROCESS_CANDIDATES process per downloaded .smi.gz file.
  ch_smi_gz = RETRIEVE_CANDIDATES.out.candidates
    .flatten()
    .filter { file -> file.name.endsWith('.smi.gz') }

  PREPROCESS_CANDIDATES(ch_smi_gz)
  ch_versions = ch_versions.mix(PREPROCESS_CANDIDATES.out.versions)

  emit:
  candidates = RETRIEVE_CANDIDATES.out.candidates // path: downloaded candidate files
  download_log = RETRIEVE_CANDIDATES.out.log // path: aria2c.log
  parquet = PREPROCESS_CANDIDATES.out.parquet // path: per-file descriptor parquet
  versions = ch_versions // channel: [ versions.yml ]
}
