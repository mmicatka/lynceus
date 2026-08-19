// modules/local/download_pdb/main.nf

process RETRIEVE_PDB {
    container "${params.registry}/lynceus/lynceus-chem:0.1.0"
    maxRetries 2
    errorStrategy 'retry'

    input:
    tuple val(ensemble_id), val(pdb_ids)

    output:
    tuple val(ensemble_id), path("structure_dir"), emit: structure_dir

    script:
    def pdb_ids_str = pdb_ids.join(',')
    """
    lynceus-chem-retrieve-pdbs \\
        --pdb-ids ${pdb_ids_str} \\
        --outdir structure_dir
    """
}
