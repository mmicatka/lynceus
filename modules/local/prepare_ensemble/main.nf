// modules/local/prepare_ensemble/main.nf

process PREPARE_ENSEMBLE {
    container "${params.registry}/lynceus/prepare-ensemble:0.1.0"

    label 'pvc_io_retry'

    input:
    tuple val(ensemble_id), path(ensemble_dir)

    output:
    tuple val(ensemble_id), path("${ensemble_dir}_prepped"), emit: prepped

    script:
    """
    docking-prepare-ensemble \\
        --ensemble ${ensemble_dir} \\
        --output ${ensemble_dir}_prepped
    """
}
