// workflows/lynceus.nf

include { CANDIDATE } from '../subworkflows/local/candidate'
include { TARGET } from '../subworkflows/local/target'
include { SURROGATE_MODEL } from '../subworkflows/local/surrogate_model'
include { DOCKING } from '../subworkflows/local/docking'

workflow LYNCEUS {
  ch_versions = channel.empty()

  def use_local = params.candidates_local_path as boolean

  ch_uri_list = use_local ? [] : file(params.uri_list, checkIfExists: true)
  ch_local_path = use_local ? file(params.candidates_local_path, checkIfExists: true) : []
  filter_config = file(params.filter.config, checkIfExists: true)

  // Target
  TARGET(params.target.ensemble)
  ch_versions = ch_versions.mix(TARGET.out.versions)

  // Candidate
  CANDIDATE(ch_uri_list, ch_local_path, filter_config, params.filter.batch_size)
  ch_versions = ch_versions.mix(CANDIDATE.out.versions)

  DOCKING(TARGET.out.structure_dir, TARGET.out.putative_binding_sites, CANDIDATE.out.filtered_parquets, params.docking.batch_size)

  // Surrogate model (train, this includes DOCKING)
  SURROGATE_MODEL(TARGET.out.structure_dir, TARGET.out.putative_binding_sites, CANDIDATE.out.filtered_parquets)
  ch_versions = ch_versions.mix(SURROGATE_MODEL.out.versions)
}
