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

  ch_candidate_done = CANDIDATE.out.done.collect().map { true }.first()

  ch_target_input = channel.of(tuple(params.target.ensemble_id, params.target.ensemble_path))
    .ifEmpty { error("params.target.ensemble_id and params.target.ensemble_path must both be set") }

  TARGET(ch_target_input)

  ch_target_surfaces_gated = ch_candidate_done
    .combine(TARGET.out.target_surfaces)
    .map { _done, ensemble_path, sites_path -> tuple(ensemble_path, sites_path) }

  SURROGATE_TRAIN(
    params.candidates.bucket,
    ch_target_surfaces_gated,
    params.surrogate.train,
  )
}
