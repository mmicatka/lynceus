// modules/local/docking_run/main.nf

process DOCKING_RUN {
    tag "${conformational_state_id}:${site_id}"

    label 'gpu'
    label 'pvc_io_retry'
    label 'scratch'

    container "${params.registry}/lynceus/docking-run:gpu-0.1.0"
    containerOptions '--gpus all'

    input:
    tuple val(conformational_state_id), path(ensemble_manifest, stageAs: 'ensemble/manifest.json'), path(ensemble_members, stageAs: 'ensemble/members/*'), val(site_id), val(center)
    val bucket
    val candidates_key

    output:
    tuple val(conformational_state_id), val(site_id), val(out_key), emit: results

    script:
    def (cx, cy, cz) = center
    out_key = "${conformational_state_id}.${site_id}.output.parquet"
    """
    docking-run \\
        --ensemble ensemble \\
        --member-id ${conformational_state_id} \\
        --ligands-path '${candidates_key}' \\
        --use-blob-storage \\
        --bucket ${bucket} \\
        --center ${cx} ${cy} ${cz} \\
        --out-dir \$PWD/unidock_gpu_out \\
        --out-parquet ${out_key} \\
        --conformational-state-id ${conformational_state_id} \\
        --num-modes 1 \\
        --site-id ${site_id}
    """
}
