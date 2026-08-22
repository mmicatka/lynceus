// modules/local/preprocess_candidates/main.nf

process PREPROCESS_CANDIDATES {
    container "${params.registry}/lynceus/preprocess-candidates:0.1.0"

    label 'process_high'
    label 'pvc_io_retry'

    input:
    path smi_gz
    val bucket

    output:
    val true, emit: done

    script:
    def prefix = smi_gz.simpleName
    """
    preprocess-candidates \\
        --input ${smi_gz} \\
        --output candidates/preprocessed/${prefix}.parquet \\
        --use-blob-storage \\
        --bucket ${bucket} \\
    """
}
