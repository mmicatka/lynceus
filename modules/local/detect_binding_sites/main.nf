// modules/local/detect_binding_sites/main.nf

process DETECT_BINDING_SITES {
    container "${params.registry}/lynceus/detect-binding-sites:0.1.0"

    input:
    tuple val(ensemble_id), path(ensemble_path)

    output:
    tuple val(ensemble_id), path("sites.json"), emit: sites

    script:
    """
    detect-binding-sites \\
    --ensemble ${ensemble_path} \\
    --out sites.json
    """
}
