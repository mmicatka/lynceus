// subworkflows/local/features/main.nf

include { GENERATE_FEATURES } from '../../../modules/local/generate_features'

workflow FEATURES {
    take:
    bucket
    config
    candidate_ready
    target_ready

    main:
    prefix = config.input_prefix.toString().replaceAll('/$', '')
    input_glob = bucket ? "s3://${bucket}/${prefix}/*.parquet" : "${prefix}/*.parquet"

    ch_shards = candidate_ready
        .collect()
        .combine(target_ready.collect())
        .flatMap { files(input_glob) }
        .map { f -> tuple("${config.input_prefix}/${f.name}", "${config.output_prefix}/${f.name}") }

    GENERATE_FEATURES(
        ch_shards,
        bucket,
        config.features,
    )

    emit:
    done = GENERATE_FEATURES.out.done.collect()
}
