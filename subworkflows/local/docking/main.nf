// subworkflows/local/docking/main.nf

include { DOCKING_PREP_TARGET ; DOCKING_PREP_CANDIDATE } from '../../../modules/local/docking_prep'
include { DETECT_PUTATIVE_BINDING_SITES } from '../../../modules/local/detect_putative_binding_sites'

workflow DOCKING {
    take:
    target_protein_conformational_ensemble // protein conformational ensemble
    candidates // path: candidate parquet

    main:
    ch_versions = channel.empty()

    DOCKING_PREP_TARGET(target_protein_conformational_ensemble)
    DETECT_PUTATIVE_BINDING_SITES(target_protein_conformational_ensemble)

    DOCKING_PREP_CANDIDATE(candidates)

    emit:
    versions = ch_versions
}
