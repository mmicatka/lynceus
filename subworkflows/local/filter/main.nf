// subworkflows/local/filter/main.nf

include { FEATURES } from '../features'

workflow FILTER {
    take:
    config
    candidate_ready
    target_ready

    main:
    FEATURES(config.bucket, config.features, candidate_ready, target_ready)
    ch_features_done = FEATURES.out.done

    emit:
    done = ch_features_done
}
