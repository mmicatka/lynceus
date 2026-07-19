// modules/local/generate_manifest/main.nf

process GENERATE_MANIFEST {
    container 'lynceus/protein-conformational-ensemble:0.1.0'

    input:
    tuple val(ensemble_id), path(ensemble_dir)

    output:
    tuple val(ensemble_id), path("${ensemble_id}"), emit: pce_package
    path "versions.yml", emit: versions

    script:
    """
    generate-manifest \\
        --members-dir ${ensemble_dir} \\
        --ensemble-id ${ensemble_id} \\
        --outdir ${ensemble_id}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        pce: \$(python -c "import pce; print(pce.__version__)" 2>/dev/null || echo "unknown")
    END_VERSIONS
    """

    stub:
    """
    mkdir -p ${ensemble_id}
    touch ${ensemble_id}/manifest.yaml

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version | sed 's/Python //')
        pce: "stub"
    END_VERSIONS
    """
}
