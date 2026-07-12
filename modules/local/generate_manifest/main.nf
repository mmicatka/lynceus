// modules/local/generate_manifest/main.nf

process GENERATE_MANIFEST {
  tag "${ensemble_id}"
  label 'process_single'
  container 'lynceus/generate-manifest:latest'

  input:
  tuple val(ensemble_id), path(members_dir)
  path config_yaml

  output:
  tuple val(ensemble_id), path("${ensemble_id}"), emit: pce_package
  path "versions.yml", emit: versions

  script:
  """
    python -m src.generate_manifest \\
        --members-dir ${members_dir} \\
        --ensemble-id ${ensemble_id} \\
        --config ${config_yaml} \\
        --outdir ${ensemble_id}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version | sed 's/Python //')
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
