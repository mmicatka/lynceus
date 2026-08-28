// modules/local/docking_prep/main.nf

process DOCKING_PREP_TARGET {
    tag "${ensemble_id}"
    container "${params.registry}/lynceus/docking-prep:0.1.0"

    label 'pvc_io_retry'

    input:
    tuple val(ensemble_id), path(ensemble_dir)

    output:
    tuple val(ensemble_id), path("${ensemble_id}_prepped"), emit: prepped

    script:
    """
    docking-prepare-ensemble \\
        --ensemble ${ensemble_dir} \\
        --output ${ensemble_id}_prepped
    """
}
