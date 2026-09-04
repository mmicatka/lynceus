// modules/local/detect_binding_sites/main.nf

process DETECT_BINDING_SITES {
    container "${params.registry}/lynceus/detect-binding-sites:0.1.0"

    input:
    tuple val(ensemble_id), path(ensemble_manifest, stageAs: 'ensemble/manifest.json'), path(ensemble_members, stageAs: 'ensemble/members/*')

    output:
    tuple val(ensemble_id), path("sites.json"), emit: sites

    script:
    """
    detect-binding-sites \\
    --ensemble ensemble \\
    --out sites.json
    """
}
