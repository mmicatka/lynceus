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

  ch_target_input = channel.of(tuple(params.target.id, params.target.path))

  TARGET(ch_target_input)

  SURROGATE_TRAIN(
    params.candidates.bucket,
    TARGET.out.target_surfaces,
    params.surrogate.train,
  )
}
