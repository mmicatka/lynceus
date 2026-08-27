// modules/local/generate_manifest/main.nf

process GENERATE_MANIFEST {
    container "${params.registry}/lynceus/generate-manifest:0.1.0"

    label 'pvc_io_retry'

    input:
    tuple val(ensemble_id), path(ensemble_dir)

    output:
    tuple val(ensemble_id), path("${ensemble_id}"), emit: protein_conformational_ensemble

    script:
    """
    generate-manifest \\
        --members-dir ${ensemble_dir} \\
        --ensemble-id ${ensemble_id} \\
        --outdir ${ensemble_id}
    """
}
