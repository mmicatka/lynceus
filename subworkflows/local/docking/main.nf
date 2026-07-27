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
    ch_versions = ch_versions.mix(DOCKING_PREP_TARGET.out.versions)

    DOCKING_CANDIDATE_PREP(candidates)
    ch_versions = ch_versions.mix(DOCKING_CANDIDATE_PREP.out.versions)

    emit:
    prepped_target = DOCKING_PREP_TARGET.out.prepped
    version = ch_versions // channel: [ versions.yml ]
}

workflow DOCKING_TARGET_PREP {
    take:
    target_protein_conformational_ensemble // protein conformational ensemble

    main:
    ch_versions = channel.empty()

    DOCKING_PREP_TARGET(target_protein_conformational_ensemble)
    ch_versions = ch_versions.mix(DETECT_PUTATIVE_BINDING_SITES.out.versions)

    DETECT_PUTATIVE_BINDING_SITES(target_protein_conformational_ensemble)
    ch_versions = ch_versions.mix(DETECT_PUTATIVE_BINDING_SITES.out.versions)

    emit:
    prepped_target = DOCKING_PREP_TARGET.out.prepped
    versions = ch_versions // channel: [ versions.yml ]
}

workflow DOCKING_CANDIDATE_PREP {
    take:
    candidates // path: candidate parquet

    main:
    DOCKING_PREP_CANDIDATE(candidates)

    emit:
    preppared = DOCKING_PREP_CANDIDATE.out.preppared
}
