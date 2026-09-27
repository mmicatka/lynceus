// modules/local/rebalance/main.nf

process COUNT_CANDIDATES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"
    tag { folder }

    label 'pvc_io_retry'
    label 'cpu_high'

    input:
    val source
    val output
    val bucket

    output:
    val true, emit: done

    script:
    def parts = source.toString().tokenize('/')
    folder = parts.last()

    """
    count-candidates \\
        --input ${source} \\
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
    val parquet_prefix
    val bucket

    output:
    val output_key, emit: counts_json

    script:
    output_key = "${parquet_prefix}/counts.json"

    """
    merge-candidate-counts \\
        --input ${parquet_prefix} \\
        --output ${output_key} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}

process ALLOCATE_CANDIDATE_SAMPLES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"
    tag { "target_total=${target_total}" }

    label 'pvc_io_retry'
    label 'cpu_low'

    input:
    val candidate_counts_key
    val source_prefix
    val target_total
    val floor_per_source
    val bucket

    output:
    val output_key, emit: manifest_key

    script:
    output_key = "candidates/allocation_manifest.csv"
    """
    allocate-candidate-samples \\
        --candidate-counts ${candidate_counts_key} \\
        --source-prefix ${source_prefix} \\
        --target-total ${target_total} \\
        --floor-per-source ${floor_per_source} \\
        --output ${output_key} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}

process SAMPLE_CANDIDATES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"
    tag { folder }

    label 'pvc_io_retry'
    label 'cpu_medium'

    input:
    tuple val(folder), val(source), val(target_count), val(source_count)
    val output_prefix
    val bucket

    output:
    tuple val(folder), val(output_key), emit: sample
    val true, emit: done

    script:
    output_key = "${output_prefix.toString().replaceAll('/$', '')}/${folder}_sample.parquet"
    """
    sample-candidates \\
        --input ${source} \\
        --target-count ${target_count} \\
        --source-count ${source_count} \\
        --output ${output_key} \\
        --use-blob-storage \\
        --bucket ${bucket} \\
        --num-workers ${task.cpus}
    """
}

process SHARD_SAMPLES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    label 'pvc_io_retry'
    label 'cpu_high'

    input:
    val source_glob
    val candidates_per_shard
    val output
    val bucket

    output:
    val "${output}/shard_manifest.jsonl", emit: shard_manifest

    script:
    """
    shard-candidate-samples \\
        --input ${source_glob} \\
        --candidates-per-shard ${candidates_per_shard} \\
        --output ${output} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}
