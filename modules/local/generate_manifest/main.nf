// modules/local/generate_manifest/main.nf

process GENERATE_MANIFEST {
    container "${params.registry}/lynceus/protein-conformational-ensemble:0.1.0"

    input:
    tuple val(ensemble_id), path(ensemble_dir)

    output:
    tuple val(ensemble_id), path("${ensemble_id}"), emit: protein_conformational_ensemble
    path "versions.yml", emit: versions

    script:
    """
    generate-manifest \\
        --members-dir ${ensemble_dir} \\
        --ensemble-id ${ensemble_id} \\
        --outdir ${ensemble_id}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        protein_conformational_ensemble: \$(python -c "import protein_conformational_ensemble; print(protein_conformational_ensemble.__version__)" 2>/dev/null || echo "unknown")
    END_VERSIONS
    """

    stub:
    """
    mkdir -p ${ensemble_id}
    touch ${ensemble_id}/manifest.yaml

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version | sed 's/Python //')
        protein_conformational_ensemble: "stub"
    END_VERSIONS
    """
}
