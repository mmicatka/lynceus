// subworkflows/local/filter/main.nf

include { GENERATE_FEATURES } from '../../../modules/local/generate_features'

workflow FILTER {
    take:
    config
    candidate_ready
    target_ready

    main:
    bucket = config.bucket
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
