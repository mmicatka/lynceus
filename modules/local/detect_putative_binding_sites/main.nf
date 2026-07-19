// modules/local/detect_putative_binding_sites/main.nf

process DETECT_PUTATIVE_BINDING_SITES {
    debug true

    container 'lynceus/detect-putative-binding-sites:0.1.0'

    input:
    tuple val(ensemble_id), path(ensemble_dir)

    output:
    tuple val(ensemble_id), path("${ensemble_id}.sites.json"), emit: sites

    script:
    """
    python3 -m detect_putative_binding_sites.detect_putative_binding_sites \\
        --ensemble ${ensemble_dir} \\
        --out ${ensemble_id}.sites.json
    """
}
