// modules/local/generate_pce_manifest/main.nf

process GENERATE_PCE_MANIFEST {
    container "${params.registry}/lynceus/generate-pce-manifest:0.1.0"

    label 'pvc_io_retry'

    input:
    tuple val(ensemble_id), path(ensemble_dir)

    output:
    path ("${ensemble_id}"), emit: done

    script:
    """
    generate-manifest \\
        --input-path ${ensemble_dir} \\
        
        --ensemble-id ${ensemble_id} \\
        --outdir ${ensemble_id}
    """
}
