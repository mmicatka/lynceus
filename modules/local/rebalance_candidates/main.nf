// modules/local/rebalance/main.nf

process COUNT_CANDIDATES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"
    tag { folder }

    input:
    val source
    val bucket

    output:
    val output_key, emit: count

    script:
    def parts = source.toString().tokenize('/')
    if (parts.size() < 2) {
        throw new IllegalArgumentException("source=${source} has no parent directory")
    }
    folder = parts.last()
    parent_dir = parts[0..-2].join('/')
    output_key = "${parent_dir}/${folder}_count.json"
    """
    count-candidates \\
        --input ${source} \\
        --output ${output_key} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}

process MERGE_CANDIDATE_COUNTS {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    input:
    val count_keys
    val bucket

    output:
    val output_key, emit: counts_json

    script:
    output_key = "candidates/raw/candidate_counts.json"
    def keys_arg = count_keys.join(',')
    """
    merge-candidate-counts \\
        --input ${keys_arg} \\
        --output ${output_key} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}
