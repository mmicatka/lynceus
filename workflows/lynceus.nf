// workflows/lynceus.nf

include { CANDIDATE } from '../subworkflows/local/candidate'
include { TARGET } from '../subworkflows/local/target'

workflow LYNCEUS {
  CANDIDATE(
    params.candidates.bucket,
    params.candidates.num_per_shard,
    params.candidates.filter_config,
  )

  TARGET(params.target)
}
