// modules/local/physiochemical_filter/main.nf


process PHYSIOCHEMICAL_FILTER {
    container "${params.registry}/lynceus/physiochemical-filter:0.1.0"

    label 'pvc_io_retry'

    input:
    path candidates
    path filter_config

    output:
    path "*.parquet", emit: filtered

    when:
    task.ext.when == null || task.ext.when

    script:
    def prefix = candidates.simpleName
    """
    physiochemical-filter \\
        --input ${candidates} \\
        --config ${filter_config} \\
        --output ${prefix}.filtered.parquet
    """
}
