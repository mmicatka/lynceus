// workflows/lynceus.nf

include { CANDIDATE } from '../subworkflows/local/candidate'

workflow LYNCEUS {
  CANDIDATE(params.candidates.bucket, params.candidates.filter_config, params.candidates.num_per_shard)
}
