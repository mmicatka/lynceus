// modules/local/download_pdb/main.nf

process RETRIEVE_PDB {
    tag "${ensemble_id}"
    label 'process_single'
    container 'lynceus/retrieve-pdb:0.1.0'
    maxRetries 2
    errorStrategy 'retry'

    input:
    tuple val(ensemble_id), val(pdb_ids)

    output:
    tuple val(ensemble_id), path("structure_dir"), emit: structure_dir
    path "versions.yml", emit: versions

    script:
    def pdb_ids_str = pdb_ids.join(' ')
    """
    python -m retrieve_pdb.retrieve_pdb \\
        --pdb-ids ${pdb_ids_str} \\
        --outdir structure_dir

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version | sed 's/Python //')
        httpx: \$(python -c "import httpx; print(httpx.__version__)")
    END_VERSIONS
    """

    stub:
    def pdb_ids_str = pdb_ids.join(' ')
    """
    mkdir -p structure_dir
    for id in ${pdb_ids_str}; do
        touch "structure_dir/\${id}.cif"
    done

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version | sed 's/Python //')
        httpx: "stub"
    END_VERSIONS
    """
}
