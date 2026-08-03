// subworkflows/local/surrogate_model/main.nf

include { SAMPLE_CANDIDATES } from '../../../modules/local/sample_candidates'
include { DOCKING } from '../docking'

workflow SURROGATE_MODEL_TRAIN {
    take:
    protein_conformational_ensemble // protein conformational ensemble
    candidates // path: filtered + repartitioned candidate parquets
    training_config // training configuration

    main:
    SAMPLE_CANDIDATES(candidates, training_config.num_samples)
    DOCKING(protein_conformational_ensemble, SAMPLE_CANDIDATES.out.candidates)

    emit:
    sampled_candidates = SAMPLE_CANDIDATES.out.candidates
    results = DOCKING.out.results
}
