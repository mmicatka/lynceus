// subworkflows/local/docking/main.nf

include { DOCKING_PREP_TARGET ; DOCKING_PREP_CANDIDATE } from '../../../modules/local/docking_prep'
include { DETECT_PUTATIVE_BINDING_SITES } from '../../../modules/local/detect_putative_binding_sites'

workflow DOCKING {
    take:
    target_pce // protein conformational ensemble
    candidates // path: candidate parquet

    main:
    ch_versions = channel.empty()

    DOCKING_PREP_TARGET(target_pce)
    DETECT_PUTATIVE_BINDING_SITES(target_pce)

    emit:
    versions = ch_versions
}
