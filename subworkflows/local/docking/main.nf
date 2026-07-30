// subworkflows/local/docking/main.nf

include { DOCKING_PREP_TARGET ; DOCKING_PREP_CANDIDATE_CONFORMER_GENERATE ; DOCKING_PREP_CANDIDATE_CONVERT_PDBQT } from '../../../modules/local/docking_prep'
include { DETECT_PUTATIVE_BINDING_SITES } from '../../../modules/local/detect_putative_binding_sites'


workflow DOCKING {
    take:
    target_protein_conformational_ensemble // protein conformational ensemble
    candidates // path: candidate parquet

    main:

    // Prep
    DOCKING_PREP_TARGET(target_protein_conformational_ensemble)
    DETECT_PUTATIVE_BINDING_SITES(target_protein_conformational_ensemble)

    DOCKING_PREP_CANDIDATE_CONFORMER_GENERATE(candidates)
    DOCKING_PREP_CANDIDATE_CONVERT_PDBQT(DOCKING_PREP_CANDIDATE_CONFORMER_GENERATE.out.conformers)

    emit:
    target = DOCKING_PREP_TARGET.out.prepped
    candidates = DOCKING_PREP_CANDIDATE_CONVERT_PDBQT.out.candidates
}
