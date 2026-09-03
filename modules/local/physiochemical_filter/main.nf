// modules/local/physiochemical_filter/main.nf


process PHYSIOCHEMICAL_FILTER {
    container "${params.registry}/lynceus/physiochemical-filter:0.1.0"

    label 'pvc_io_retry'

    input:
    path candidate
    val filter_config
    val bucket

    output:
    val (candidate), emit: done

    when:
    task.ext.when == null || task.ext.when

    script:
    def prefix = candidate.simpleName
    def mw_min    = filter_config?.molecular_weight?.min != null ? "--mol-weight-min ${filter_config.molecular_weight.min}" : ""
    def mw_max    = filter_config?.molecular_weight?.max != null ? "--mol-weight-max ${filter_config.molecular_weight.max}" : ""
    def ha_min    = filter_config?.heavy_atom?.min != null       ? "--heavy-atom-min ${filter_config.heavy_atom.min}" : ""
    def ha_max    = filter_config?.heavy_atom?.max != null       ? "--heavy-atom-max ${filter_config.heavy_atom.max}" : ""
    def cns_mpo   = (filter_config?.cns_mpo?.enabled && filter_config?.cns_mpo?.min_score != null) ? "--cns-mpo ${filter_config.cns_mpo.min_score}" : ""
    def use_pains = filter_config?.pains?.enabled ? "--use-pains" : ""
    """
    physiochemical-filter \\
        --input ${candidate} \\
        --output candidates/filtered/${prefix}.parquet \\
        --use-blob-storage \\
        --bucket ${bucket} \\
        ${mw_min} \\
        ${mw_max} \\
        ${ha_min} \\
        ${ha_max} \\
        ${cns_mpo} \\
        ${use_pains}
    """
}
