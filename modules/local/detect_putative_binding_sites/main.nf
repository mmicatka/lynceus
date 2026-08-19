// modules/local/detect_putative_binding_sites/main.nf

process DETECT_PUTATIVE_BINDING_SITES {
    container "${params.registry}/lynceus/detect-putative-binding-sites:0.1.0"

    input:
    tuple val(ensemble_id), path(ensemble_dir)

    output:
    path ("${ensemble_id}.sites.json"), emit: sites

    script:
    """
    detect-putative-binding-sites \\
        --ensemble ${ensemble_dir} \\
        --out ${ensemble_id}.sites.json
    """
}
