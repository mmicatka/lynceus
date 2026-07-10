// workflows/lynceus.nf

include { CANDIDATE } from '../subworkflows/candidate/main'

workflow LYNCEUS {

  main:
  ch_versions = channel.empty()

  def use_local = params.candidates_local_path as boolean

  ch_uri_list = use_local ? [] : file(params.uri_list, checkIfExists: true)
  ch_local_path = use_local ? file(params.candidates_local_path, checkIfExists: true) : []
  filter_config = file(params.filter.config, checkIfExists: true)

  CANDIDATE(ch_uri_list, ch_local_path, filter_config, params.filter.batch_size)
  ch_versions = ch_versions.mix(CANDIDATE.out.versions)

  emit:
  candidates = CANDIDATE.out.candidates
  parquet = CANDIDATE.out.parquet
  versions = ch_versions
}
