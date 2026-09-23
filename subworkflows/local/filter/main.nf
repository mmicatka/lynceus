// subworkflows/local/filter/main.nf

include { GENERATE_FEATURES } from '../../../modules/local/generate_features'

workflow FILTER {
    take:
    config
    candidate_ready
    target_ready

    main:
    candidate_ready.collect()
    target_ready.collect()

    bucket = config.bucket

    input_glob = "${config.input_prefix.toString().replaceAll('/$', '')}/*.parquet"

    ch_shards = channel.fromPath(bucket ? "s3://${bucket}/${input_glob}" : input_glob)
        .map { f ->
            def input_key = "${config.input_prefix}/${f.name}"
            def output_key = "${config.output_prefix}/${f.name.replaceFirst(/\.parquet$/, '_features.parquet')}"
            tuple(input_key, output_key)
        }

    GENERATE_FEATURES(
        ch_shards,
        bucket,
        config.features,
    )

    emit:
    done = GENERATE_FEATURES.out.done.collect()
}
