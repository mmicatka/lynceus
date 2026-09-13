// modules/local/rebalance/main.nf

process COUNT_CANDIDATES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    input:
    val source
    val bucket

    output:
    path "${folder}_count.json", emit: count

    script:
    folder = source.toString().tokenize('/').last()
    """
    count-candidates \\
        --input ${source} \\
        --output ${folder}_count.json \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}
