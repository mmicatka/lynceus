// modules/local/detect_putative_sites/main.nf

process DETECT_PUTATIVE_SITES {
    debug true

    input:
    tuple val(ensemble_id), path(ensemble_dir)

    output:
    path ("${ensemble_id}.sites.json"), emit: sites

    script:
    """
    python3 -m detect_putative_sites.detect_putative_sites \\
        --ensemble ${ensemble_dir} \\
        --out ${ensemble_id}.sites.json
    """
}
