// modules/local/split_candidates/main.nf

process SPLIT_CANDIDATES {
  tag "${meta.id}"

  container "lynceus/split-candidates:0.1.0"

  input:
  tuple val(meta), path(candidates_parquet), val(chunk_size)

  output:
  tuple val(meta), path("chunks/*.parquet"), emit: chunks
  path "versions.yml", emit: versions

  script:
  """
  python3 -m split_candidates.split_candidates \\
      --candidates-parquet '${candidates_parquet}' \\
      --chunk-size ${chunk_size} \\
      --output-dir chunks

  cat <<-END_VERSIONS > versions.yml
  "${task.process}":
      pandas: \$(python3 -c "import pandas; print(pandas.__version__)")
  END_VERSIONS
  """

  stub:
  """
  mkdir -p chunks
  touch chunks/chunk_0000.parquet

  cat <<-END_VERSIONS > versions.yml
  "${task.process}":
      pandas: \$(python3 -c "import pandas; print(pandas.__version__)")
  END_VERSIONS
  """
}
