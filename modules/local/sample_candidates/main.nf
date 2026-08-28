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
    def config_json = groovy.json.JsonOutput.toJson(strategy_config)
    """
    sample-candidates \\
        --input-path '${input_path}' \\
        --output-path ${output_path} \\
        --strategy-config '${config_json}' \\
        --use-blob-storage \\
        --bucket ${bucket}
    """
}
