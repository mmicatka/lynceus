// modules/local/docking_prep/main.nf

process DOCKING_PREP_TARGET {
    container 'lynceus/docking-prep:0.1.0'

    input:
    tuple val(ensemble_id), path(ensemble_dir)

    script:
    """
    docking-prep-ensemble \\
        --ensemble ${ensemble_dir} \\
        --output ${ensemble_id}_prepped
    """
}

process DOCKING_PREP_CANDIDATE {
    container 'lynceus/docking-prep:0.1.0'

    input:
    path candidates

    script:
    """
    """
}
