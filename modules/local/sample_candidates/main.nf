// modules/local/sample_candidates/main.nf

process SAMPLE_CANDIDATES {
    container "${params.registry}/lynceus/sample-candidates:0.1.0"

    input:
    val input_path
    val output_path
    val bucket
    val config

    output:
    val true, emit: done

    script:
    """
    """
}
