// modules/local/preprocess_candidates/main.nf

process PREPROCESS_CANDIDATES {
    container "${params.registry}/lynceus/preprocess-candidates:0.1.0"

    label 'process_high'
    label 'pvc_io_retry'

    input:
    path smi_gz
    val output_uri_prefix

    output:
    val true, emit: done

    script:
    def prefix = smi_gz.simpleName
    """
    preprocess-candidates \\
        --input ${smi_gz} \\
        --output-uri ${params.s3_endpoint}/${output_uri_prefix}/${prefix}.parquet \\
        --s3-endpoint '${params.s3_endpoint}' \\
        --s3-region '${params.s3_region ?: "garage"}' \\
        --s3-url-style '${params.s3_url_style ?: "path"}'
    """
}
