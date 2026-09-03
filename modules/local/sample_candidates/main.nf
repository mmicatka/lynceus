// modules/local/sample_candidates/main.nf

process SAMPLE_CANDIDATES {
    container "${params.registry}/lynceus/sample-candidates:0.1.0"

    input:
    val input_path
    val output_path
    val bucket
    val strategy_config

    output:
    val true, emit: done

    script:
    def field_args = [
        '--field morgan_fingerprint:array:32',
        '--field molecular_weight:scalar',
        '--field calculated_distribution_coefficient:scalar',
        '--field topological_polar_surface_area:scalar',
    ].join(' ')

    """
    sample-candidates \\
        --input '${input_path}' \\
        --output ${output_path} \\
        ${field_args} \\
        --random-seed ${strategy_config.seed} \\
        --target-total-samples ${strategy_config.num_samples} \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}
