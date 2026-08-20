// workflows/lynceus.nf

include { CANDIDATE } from '../subworkflows/local/candidate'

workflow LYNCEUS {
  ch_uri_list = file(params.candidates.uri_list, checkIfExists: true)

  CANDIDATE(ch_uri_list, params.candidates.filter_config, params.candidates.num_shards)
}
