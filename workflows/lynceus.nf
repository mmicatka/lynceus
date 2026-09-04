// workflows/lynceus.nf

include { CANDIDATE } from '../subworkflows/local/candidate'
include { TARGET } from '../subworkflows/local/target'
include { SURROGATE_TRAIN } from '../subworkflows/local/surrogate'
include { DOCKING } from '../subworkflows/local/docking'

workflow LYNCEUS {
  CANDIDATE(
    params.candidates
  )

  ch_candidate_done = CANDIDATE.out.done.collect().map { true }

  if (!params.target?.ensemble_id) {
    error("params.target.ensemble_id must be set")
  }
  if (!params.target?.ensemble_path) {
    error("params.target.ensemble_path must be set")
  }

  ch_target_input = channel.of(tuple(params.target.ensemble_id, params.target.ensemble_path))
    .map { id, ensemble_path ->
      def manifest = file("${ensemble_path}/manifest.json")
      if (!manifest.exists()) {
        error("manifest.json not found at ${ensemble_path} for ensemble ${id}")
      }
      def members = files("${ensemble_path}/members/*")
      if (members.isEmpty()) {
        error("No member structure files found under ${ensemble_path}/members for ensemble ${id}")
      }
      tuple(id, manifest, members)
    }

  TARGET(ch_target_input)

  ch_target_surfaces_gated = ch_candidate_done
    .combine(TARGET.out.target_surfaces)
    .map { done, ensemble_dir, sites_path -> tuple(done, ensemble_dir, sites_path) }

  SURROGATE_TRAIN(
    params.candidates.bucket,
    ch_target_surfaces_gated,
    params.surrogate.train,
  )
}
