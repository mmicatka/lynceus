// modules/local/download_pdb/main.nf

process RETRIEVE_PDB {
  tag "${ensemble_id}:${pdb_id}"
  label 'process_single'
  container "quay.io/biocontainers/aria2:1.36.0"
  containerOptions '--entrypoint ""'

  input:
  tuple val(ensemble_id), val(pdb_id)

  output:
  tuple val(ensemble_id), path("structure_dir"), emit: structure_dir
  path "versions.yml", emit: versions

  script:
  """
    set -euo pipefail

    PDB_ID_UPPER=\$(echo "${pdb_id}" | tr '[:lower:]' '[:upper:]')
    mkdir -p structure_dir

    if aria2c --max-tries=3 --retry-wait=2 --quiet=true \\
        --dir structure_dir --out "\${PDB_ID_UPPER}.cif" \\
        "https://files.rcsb.org/download/\${PDB_ID_UPPER}.cif"; then
        DOWNLOADED="structure_dir/\${PDB_ID_UPPER}.cif"
    elif aria2c --max-tries=3 --retry-wait=2 --quiet=true \\
        --dir structure_dir --out "\${PDB_ID_UPPER}.pdb" \\
        "https://files.rcsb.org/download/\${PDB_ID_UPPER}.pdb"; then
        DOWNLOADED="structure_dir/\${PDB_ID_UPPER}.pdb"
    else
        echo "FATAL: failed to download \${PDB_ID_UPPER} as .cif or .pdb from RCSB" >&2
        exit 1
    fi

    if [ ! -s "\${DOWNLOADED}" ]; then
        echo "FATAL: downloaded file \${DOWNLOADED} is empty" >&2
        exit 1
    fi

    echo "Downloaded ${pdb_id} -> \${DOWNLOADED}"

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        aria2c: \$(aria2c --version | head -n1 | sed 's/aria2 version //')
    END_VERSIONS
    """

  stub:
  """
    mkdir -p structure_dir
    touch structure_dir/${pdb_id}.cif

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        aria2c: "stub"
    END_VERSIONS
    """
}
