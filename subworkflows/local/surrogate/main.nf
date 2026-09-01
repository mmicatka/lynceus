// subworkflows/local/surrogate_model/main.nf

include { SAMPLE_CANDIDATES } from '../../../modules/local/sample_candidates'
include { DOCKING } from '../docking'

workflow SURROGATE_TRAIN {
    take:
    bucket // bucket
    target_surfaces // tuple: ensemble_id, sites (path), prepped (path) — from TARGET.out.target_surfaces
    config // training configuration

    main:
    input_path = "s3://${bucket}/candidates/rebalanced"
    output_path = "s3://${bucket}/candidates/sampled"

    SAMPLE_CANDIDATES(input_path, output_path, bucket, config.sample)
    DOCKING(target_surfaces, SAMPLE_CANDIDATES.out.done, output_path)

    emit:
    sampled_candidates_path = output_path
    results = DOCKING.out.results
}
