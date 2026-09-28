// modules/local/rebalance/main.nf

process LOAD_CANDIDATES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    label 'pvc_io_retry'
    label 'cpu_high'

    input:
    val input
    val output
    val bucket

    output:
    val true, emit: done

    script:
    """
    load-candidates \\
        --input ${input} \\
        --output ${output} \\
        --use-blob-storage \\
        --bucket ${bucket} \\
        --num-workers ${task.cpus}
    """
}

process MERGE_CANDIDATE_COUNTS {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    label 'pvc_io_retry'
    label 'cpu_low'

    input:
    val input
    val bucket

    output:
    val output_key, emit: counts_json

    script:
    output_key = "${input}/counts.json"

    """
    merge-candidate-counts \\
        --input ${input} \\
        --output ${output_key} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}

process ALLOCATE_CANDIDATE_SAMPLES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    label 'pvc_io_retry'
    label 'cpu_low'

    input:
    val candidate_counts
    val source_prefix
    val target_total
    val floor_per_source
    val output
    val bucket

    output:
    val output, emit: manifest_key

    script:
    """
    allocate-candidate-samples \\
        --candidate-counts ${candidate_counts} \\
        --source-prefix ${source_prefix} \\
        --target-total ${target_total} \\
        --floor-per-source ${floor_per_source} \\
        --output ${output} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}

process SAMPLE_CANDIDATES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    label 'pvc_io_retry'
    label 'cpu_med'

    input:
    tuple val(input), val(output), val(source_count), val(target_count)
    val file_size_bytes
    val bucket

    output:
    val true, emit: done

    script:
    """
    sample-candidates \\
        --input ${input} \\
        --output ${output} \\
        --target-count ${target_count} \\
        --source-count ${source_count} \\
        --file-size-bytes ${file_size_bytes} \\
        --use-blob-storage \\
        --bucket ${bucket} \\
        --num-workers ${task.cpus}
    """
}

process SHARD_CANDIDATES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    label 'pvc_io_retry'
    label 'cpu_med'

    input:
    tuple val(input), val(output)
    val num_shards
    val bucket

    output:
    val true, emit: done

    script:
    """
    shard-candidates \\
        --input ${input} \\
        --output ${output} \\
        --num-shards ${num_shards} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}

process CONCAT_CANDIDATE_SHARDS {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    label 'pvc_io_retry'
    label 'cpu_med'

    input:
    tuple val(input), val(output)
    val bucket

    output:
    val true, emit: done

    script:
    """
    concat-candidate-shards \\
        --input ${input} \\
        --output ${output} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}
