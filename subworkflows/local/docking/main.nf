// subworkflows/local/docking/main.nf

include { DOCKING_PREP_TARGET ; DOCKING_PREP_CANDIDATE } from '../../../modules/local/docking_prep'
include { DETECT_PUTATIVE_BINDING_SITES } from '../../../modules/local/detect_putative_binding_sites'

workflow DOCKING {
    take:
    target_protein_conformational_ensemble // protein conformational ensemble
    candidates // path: candidate parquet

    main:
    DOCKING_PREP_TARGET(target_protein_conformational_ensemble)
    DOCKING_CANDIDATE_PREP(candidates)

    emit:
    prepped_target = DOCKING_PREP_TARGET.out.prepped
}

workflow DOCKING_TARGET_PREP {
    take:
    target_protein_conformational_ensemble // protein conformational ensemble

    main:
    DOCKING_PREP_TARGET(target_protein_conformational_ensemble)
    DETECT_PUTATIVE_BINDING_SITES(target_protein_conformational_ensemble)

    emit:
    prepped_target = DOCKING_PREP_TARGET.out.prepped
}

workflow DOCKING_CANDIDATE_PREP {
    take:
    candidates // path: candidate parquet

    main:
    DOCKING_PREP_CANDIDATE(candidates)

    emit:
    prepped = DOCKING_PREP_CANDIDATE.out.prepped
}
