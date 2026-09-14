// modules/local/rebalance/main.nf

process COUNT_CANDIDATES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"
    tag { folder }

    label 'pvc_io_retry'

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
        --bucket ${bucket} \\
        --num-workers ${task.cpus}
    """
}

process MERGE_CANDIDATE_COUNTS {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"

    label 'pvc_io_retry'

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

process ALLOCATE_CANDIDATE_SAMPLES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"
    tag { "target_total=${target_total}" }

    label 'pvc_io_retry'

    input:
    val candidate_counts_key
    val source_prefix
    val target_total
    val floor_per_source
    val bucket

    output:
    val output_key, emit: manifest_key

    script:
    output_key = "allocation_manifest.csv"
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

    input:
    tuple val(folder), val(source), val(target_count)
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
        --output ${output_key} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}

process SHARD_SAMPLES {
    container "${params.registry}/lynceus/rebalance-candidates:0.1.0"
    tag { "n_shards=${n_shards}" }

    label 'pvc_io_retry'

    input:
    val ready
    val source_glob
    val n_shards
    val output
    val bucket

    output:
    val "${output}/shard_manifest.jsonl", emit: shard_manifest

    script:
    """
    shard-candidate-samples \\
        --input ${source_glob} \\
        --n-shards ${n_shards} \\
        --output ${output} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}
