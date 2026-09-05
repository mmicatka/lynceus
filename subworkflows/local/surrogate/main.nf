// subworkflows/local/surrogate_model/main.nf

include { SAMPLE_CANDIDATES } from '../../../modules/local/sample_candidates'
include { DOCKING } from '../docking'

workflow SURROGATE_TRAIN {
    take:
    bucket
    target_surfaces // tuple: candidate_done, manifest (path), members (path), sites (path)
    config

    main:
    input_path = "candidates/rebalanced/**/*.parquet"
    output_path = "s3://lynceus/candidates/sampled.parquet"

    ch_candidate_done = target_surfaces.map { done, _manifest, _members, _sites_path -> done }.first()
    ch_target_surfaces = target_surfaces.map { _done, manifest, members, sites_path -> tuple(manifest, members, sites_path) }

    ch_gated_input_path = ch_candidate_done
        .combine(channel.of(input_path))
        .map { _done, path -> path }

    SAMPLE_CANDIDATES(ch_gated_input_path, output_path, bucket, config.sample)
    DOCKING(ch_target_surfaces, SAMPLE_CANDIDATES.out.done, output_path)

    emit:
    sampled_candidates_path = output_path
    results = DOCKING.out.results
}
