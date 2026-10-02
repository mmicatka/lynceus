// subworkflows/local/filter/main.nf

include { FEATURES } from '../features'
include { SURROGATE_TRAIN } from '../surrogate'

workflow FILTER {
    take:
    config
    candidate_ready
    target_ready

    main:
    FEATURES(config.bucket, config.features, candidate_ready)
    ch_features_done = FEATURES.out.done

    SURROGATE_TRAIN(config.bucket, config.surrogate, ch_features_done, target_ready)
}
