// modules/local/detect_binding_sites/main.nf

process DETECT_BINDING_SITES {
    container "${params.registry}/lynceus/detect-binding-sites:0.1.0"

    label 'cpu_low'

    input:
    tuple val(ensemble_id), val(ensemble_path)

    output:
    tuple val(ensemble_id), val(out_path), emit: sites

    script:
    out_path = "${ensemble_path}/sites.json"
    def bucket_opt = params.bucket ? "--bucket ${params.bucket}" : ""

    """
    detect-binding-sites \\
    --ensemble ${ensemble_path} \\
    --out ${out_path} \\
    ${bucket_opt}
    """
}
