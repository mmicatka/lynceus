// modules/local/prepare_docking_target/main.nf

process PREPARE_DOCKING_TARGET {
  tag "${conformational_state_id}"
  label 'process_single'

  container "lynceus/prepare-docking-target:0.1.0"

  input:
  tuple val(conformational_state_id), path(pce_package_dir)

  output:
  tuple val(conformational_state_id), path("*.pdbqt"), emit: pdbqt
  path "versions.yml", emit: versions

  script:
  """
  python3 -m prepare_docking_target.prepare_docking_target \\
      --pce-package-dir '${pce_package_dir}' \\
      --conformational-state-id '${conformational_state_id}' \\
      --output '${conformational_state_id}.pdbqt'

  cat <<-END_VERSIONS > versions.yml
  "${task.process}":
      gemmi: \$(python3 -c "import gemmi; print(gemmi.__version__)")
      meeko: \$(mk_prepare_receptor.py --version 2>&1 | tail -n1)
  END_VERSIONS
  """

  stub:
  """
  touch ${conformational_state_id}.pdbqt

  cat <<-END_VERSIONS > versions.yml
  "${task.process}":
      gemmi: \$(python3 -c "import gemmi; print(gemmi.__version__)")
      meeko: \$(mk_prepare_receptor.py --version 2>&1 | tail -n1)
  END_VERSIONS
  """
}
