// workflows/lynceus.nf

include { CANDIDATE } from '../subworkflows/local/candidate'
include { TARGET } from '../subworkflows/local/target'
include { SURROGATE_TRAIN } from '../subworkflows/local/surrogate'
include { DOCKING } from '../subworkflows/local/docking'

workflow LYNCEUS {
  CANDIDATE(
    params.candidates.bucket,
    params.candidates.num_per_shard,
    params.candidates.filter_config,
  )

  _ch_candidate_done = CANDIDATE.out.done.collect().ifEmpty { true }

  TARGET(params.target)

  _ch_target_done = TARGET.out.done.collect().ifEmpty { true }

  SURROGATE_TRAIN(
    CANDIDATE.out.filtered_candidates,
    TARGET.out.surfaces,
    params.surrogate.train,
  )
}
