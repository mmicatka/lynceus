// modules/local/rebalance/main.nf

process REBALANCE_CANDIDATES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    input:
    val input_uri
    val output_uri_prefix
    val num_per_shard

    output:
    val true, emit: done

    script:
    """
    rebalance-candidates \\
        --input-uri '${input_uri}' \\
        --output-uri-prefix '${output_uri_prefix}' \\
        --num-shards ${num_per_shard} \\
    """
}
