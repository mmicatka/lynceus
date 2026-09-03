// modules/local/physiochemical_filter/main.nf


process PHYSIOCHEMICAL_FILTER {
    container "${params.registry}/lynceus/physiochemical-filter:0.1.0"

    label 'pvc_io_retry'

    input:
    path candidate
    path filter_config
    val bucket

    output:
    val (candidate), emit: done

    when:
    task.ext.when == null || task.ext.when

    script:
    def prefix = candidate.simpleName
    """
    physiochemical-filter \\
        --input ${candidate} \\
        --output candidates/filtered/${prefix}.parquet \\
        --use-blob-storage \\
        --bucket ${bucket} \\

    """
}
