// subworkflows/local/surrogate_model/main.nf

include { SAMPLE_CANDIDATES } from '../../../modules/local/sample_candidates'
include { DOCKING } from '../docking'

workflow SURROGATE_TRAIN {
    take:
    bucket // bucket
    target_surfaces // tuple: ensemble_id, sites (path), prepped (path) — from TARGET.out.target_surfaces
    strategy_config // inline map: stratify_sample config
    _config // training configuration

    main:
    input_path = "s3://${bucket}/candidates"
    output_path = "s3://${bucket}/candidates/sampled"

    SAMPLE_CANDIDATES(input_path, output_path, bucket, strategy_config)
    DOCKING(target_surfaces, SAMPLE_CANDIDATES.out.done, output_path)

    emit:
    sampled_candidates_path = output_path
    results = DOCKING.out.results
}
