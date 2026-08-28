// modules/local/docking_run/main.nf

process DOCKING_RUN {
    tag "${conformational_state_id}:${site_id}"

    label 'gpu'
    label 'pvc_io_retry'

    container "${params.registry}/lynceus/docking-run:gpu-0.1.0"
    containerOptions '--gpus all'

    input:
    tuple val(conformational_state_id), path(receptor), val(site_id), val(center), val(size)
    path candidates

    output:
    tuple val(conformational_state_id), val(site_id), path("*.parquet"), emit: results

    script:
    def (cx, cy, cz) = center
    def (sx, sy, sz) = size
    """
    docking-run --provider gpu \\
        --receptor ${receptor} \\
        --ligands-path ${candidates} \\
        --center ${cx} ${cy} ${cz} \\
        --size ${sx} ${sy} ${sz} \\
        --out-parquet ${conformational_state_id}.${site_id}.output.parquet \\
        --conformational-state-id ${conformational_state_id} \\
        --num-modes 1 \\
        --site-id ${site_id}
    """
}
