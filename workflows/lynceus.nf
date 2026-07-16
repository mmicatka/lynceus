// workflows/lynceus.nf

include { CANDIDATE } from '../subworkflows/local/candidate'
include { TARGET } from '../subworkflows/local/target'
include { SURROGATE_MODEL_TRAIN } from '../subworkflows/local/surrogate_model'

workflow LYNCEUS {

  main:
  ch_versions = channel.empty()

  def use_local = params.candidates_local_path as boolean

  ch_uri_list = use_local ? [] : file(params.uri_list, checkIfExists: true)
  ch_local_path = use_local ? file(params.candidates_local_path, checkIfExists: true) : []
  filter_config = file(params.filter.config, checkIfExists: true)

  CANDIDATE(ch_uri_list, ch_local_path, filter_config, params.filter.batch_size)
  ch_versions = ch_versions.mix(CANDIDATE.out.versions)

  TARGET(params.target.ensemble)

  SURROGATE_MODEL_TRAIN(CANDIDATE.out.filtered_parquets)
  ch_versions = ch_versions.mix(SURROGATE_MODEL_TRAIN.out.versions)

  emit:
  training_candidates = SURROGATE_MODEL_TRAIN.out.training_candidates
  putative_binding_sites = TARGET.out.putative_binding_sites
  versions = ch_versions
}
