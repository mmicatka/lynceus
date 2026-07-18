// modules/local/prepare_docking_candidates/main.nf

process PREPARE_DOCKING_CANDIDATES {
  tag "${meta.id}"
  label 'process_medium'

  container "lynceus/prepare-docking-candidates:0.1.0"

  input:
  tuple val(meta), path(candidates_parquet)

  output:
  tuple val(meta), path("output/pdbqt"), path("output/prep_manifest.parquet"), emit: prepared
  path "versions.yml", emit: versions

  script:
  """
  python3 -m prepare_docking_candidates.prepare_docking_candidates \\
      --candidates-parquet '${candidates_parquet}' \\
      --output-dir output

  cat <<-END_VERSIONS > versions.yml
  "${task.process}":
      rdkit: \$(python3 -c "import rdkit; print(rdkit.__version__)")
      meeko: \$(python3 -c "import meeko; print(meeko.__version__)")
      pandas: \$(python3 -c "import pandas; print(pandas.__version__)")
  END_VERSIONS
  """

  stub:
  """
  mkdir -p output/pdbqt
  touch output/pdbqt/stub.pdbqt output/prep_manifest.parquet

  cat <<-END_VERSIONS > versions.yml
  "${task.process}":
      rdkit: \$(python3 -c "import rdkit; print(rdkit.__version__)")
      meeko: \$(python3 -c "import meeko; print(meeko.__version__)")
      pandas: \$(python3 -c "import pandas; print(pandas.__version__)")
  END_VERSIONS
  """
}
