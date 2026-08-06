// modules/local/docking_run/main.nf

process DOCKING_RUN_CPU {
    tag "${conformational_state_id}:${site_id}"
    label 'process_single'
    container 'lynceus/docking-run:cpu-0.1.0'

    input:
    tuple val(conformational_state_id), path(receptor), val(site_id), val(center), val(size)
    path candidates

    output:
    tuple val(conformational_state_id), val(site_id), path("*.parquet"), emit: results

    script:
    def (cx, cy, cz) = center
    def (sx, sy, sz) = size
    """
    docking-run --provider cpu \\
        --receptor ${receptor} \\
        --ligands ${candidates}/partitions/**/*.pdbqt \\
        --center ${cx} ${cy} ${cz} \\
        --size ${sx} ${sy} ${sz} \\
        --n-workers 2 \\
        --out-parquet output.parquet \\
        --conformational-state-id ${conformational_state_id} \\
        --site-id ${site_id}
    """
}

process DOCKING_RUN_GPU {
    tag "${conformational_state_id}:${site_id}"
    label 'process_single'
    container 'lynceus/docking-run:gpu-0.1.0'
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
        --ligands ${candidates}/partitions/**/*.pdbqt \\
        --center ${cx} ${cy} ${cz} \\
        --size ${sx} ${sy} ${sz} \\
        --out-parquet output.parquet \\
        --conformational-state-id ${conformational_state_id} \\
        --site-id ${site_id}
    """
}
