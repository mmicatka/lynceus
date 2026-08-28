// subworkflows/local/surrogate_model/main.nf

include { SAMPLE_CANDIDATES } from '../../../modules/local/sample_candidates'
include { DOCKING } from '../docking'

workflow SURROGATE_TRAIN {
    take:
    bucket // bucket
    protein_conformational_ensemble // protein conformational ensemble
    config // training configuration

    main:
    directory = "s3://${bucket}/candidates"


    SAMPLE_CANDIDATES(candidates, config.sample)
    DOCKING(protein_conformational_ensemble, SAMPLE_CANDIDATES.out.candidates)

    emit:
    sampled_candidates = SAMPLE_CANDIDATES.out.candidates
    results = DOCKING.out.results
}
