// subworkflows/local/surrogate/main.nf



def roundPrefix(model_prefix: String, round_index: int) {
    "${model_prefix}/round_${round_index}"
}

def modelKey(model_prefix: String, round_index: int) {
    round_index == 0 ? '' : "${roundPrefix(model_prefix, round_index)}/model.joblib"
}

def labelsGlob(model_prefix: String) {
    "${model_prefix}/round_*/labels.parquet"
}

def validationKey(model_prefix: String) {
    "${roundPrefix(model_prefix, 0)}/validation.parquet"
}


workflow SURROGATE_TRAIN {
    take:
    bucket
    features_config
    config
    features_done
    target_ready

    main:
    n_rounds = config.rounds.size()

    if (n_rounds < 1) {
        error("filter.surrogate.rounds must have at least one entry")
    }
    if (config.rounds[0].active != 0) {
        error("filter.surrogate.rounds[0].active must be 0, got ${config.rounds[0].active}")
    }

    ch_round0 = features_done.combine(target_ready).map { a, b -> 0 }

    updates = channel.topic('surrogate_state')
    pending = updates.until { round_index -> round_index >= n_rounds }

    ch_round_index = ch_round0.mix(pending)

    ch_sample = ch_round_index.map { round_index ->
        def spec = config.rounds[round_index]
        tuple(
            round_index,
            roundPrefix(config.model_prefix, round_index),
            modelKey(config.model_prefix, round_index),
            spec.active,
            spec.uniform,
            round_index == 0 ? config.validation : 0,
        )
    }

    SAMPLE_SURROGATE_CANDIDATES(
        bucket,
        features_config.conformer_prefix,
        features_config.feature_prefix,
        config.feature_list,
        ch_sample,
    )

    DOCKING_RUN(bucket, SAMPLE_SURROGATE_CANDIDATES.out.round)

    LABEL_DOCKING_RESULTS(bucket, DOCKING_RUN.out.round)

    ch_train = LABEL_DOCKING_RESULTS.out.round.map { round_index, round_prefix ->
        tuple(
            round_index,
            round_index + 1,
            labelsGlob(config.model_prefix),
            validationKey(config.model_prefix),
            modelKey(config.model_prefix, round_index + 1),
        )
    }

    TRAIN_SURROGATE(bucket, features_config.feature_prefix, config.feature_list, ch_train)

    ch_final_model = channel.topic('surrogate_state')
        .filter { round_index -> round_index >= n_rounds }
        .first()
        .map { round_index -> modelKey(config.model_prefix, round_index) }

    emit:
    model_key = ch_final_model
}
