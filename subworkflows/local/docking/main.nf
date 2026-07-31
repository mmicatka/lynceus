// subworkflows/local/docking/main.nf

include { DOCKING_PREP_TARGET ; DOCKING_PREP_CANDIDATE_CONFORMER_GENERATE ; DOCKING_PREP_CANDIDATE_CONVERT_PDBQT } from '../../../modules/local/docking_prep'
include { DETECT_PUTATIVE_BINDING_SITES } from '../../../modules/local/detect_putative_binding_sites'
include { DOCKING_RUN } from '../../../modules/local/docking_run'

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

    // Run docking
    DOCKING_RUN(DOCKING_PREP_TARGET.out.prepped, DETECT_PUTATIVE_BINDING_SITES.out.sites, DOCKING_PREP_CANDIDATE_CONVERT_PDBQT.out.converted)

    emit:
    target = DOCKING_PREP_TARGET.out.prepped
    sites = DETECT_PUTATIVE_BINDING_SITES.out.sites
}
