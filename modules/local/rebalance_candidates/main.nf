// modules/local/rebalance/main.nf

process REBALANCE_CANDIDATES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    input:
    val input_path
    path output_path
    val bucket
    val num_per_shard

    output:
    val true, emit: done

    script:
    """
    rebalance-candidates \\
        --input-path ${input_path} \\
        --output-path ${output_path} \\
        --num-per-shard ${num_per_shard} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}
