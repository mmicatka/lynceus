// modules/local/preprocess_candidates/main.nf

process PREPROCESS_CANDIDATES {
    container "${params.registry}/lynceus/preprocess-candidates:0.1.0"

    publishDir "s3://${params.candidate_output_bucket}/preprocessed", mode: 'copy'

    input:
    path smi_gz

    output:
    path "*.parquet", emit: processed

    when:
    task.ext.when == null || task.ext.when

    script:
    def prefix = smi_gz.simpleName
    """
    preprocess-candidates \\
        --input ${smi_gz} \\
        --output ${prefix}.parquet
    """
}
