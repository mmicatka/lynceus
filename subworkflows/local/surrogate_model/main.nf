// subworkflows/local/surrogate_model/main.nf


include { SAMPLE_CANDIDATES } from '../../../modules/local/sample_candidates'

workflow SURROGATE_MODEL_TRAIN {
    take:
    pce // protein conformational ensemble
    putative_binding_sites // putative binding sites
    candidates // path: filtered + repartitioned candidate parquets

    main:
    ch_versions = channel.empty()

    SAMPLE_CANDIDATES(candidates)
    ch_versions = ch_versions.mix(SAMPLE_CANDIDATES.out.versions)

    emit:
    training_candidates = SAMPLE_CANDIDATES.out.training_candidates // path: training_candidates.parquet
    versions = ch_versions
}
