// modules/local/preprocess_candidates/main.nf

process PREPROCESS_CANDIDATES {
  tag "${smi_gz}"
  label 'process_medium'

  container "lynceus/preprocess-candidates:0.1.0"

  publishDir "${params.outdir}/candidate/preprocess", mode: 'copy'

  input:
  path smi_gz

  output:
  path "*.parquet", emit: parquet
  path "versions.yml", emit: versions

  when:
  task.ext.when == null || task.ext.when

  script:
  def prefix = smi_gz.simpleName
  // strips both .gz and .smi (multi-extension aware)
  """
    python3 -m preprocess_candidates.preprocess \\
        --input ${smi_gz} \\
        --output ${prefix}.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        rdkit: \$(python3 -c "import rdkit; print(rdkit.__version__)")
        pandas: \$(python3 -c "import pandas; print(pandas.__version__)")
        pyarrow: \$(python3 -c "import pyarrow; print(pyarrow.__version__)")
    END_VERSIONS
    """

  stub:
  def prefix = smi_gz.simpleName
  """
    touch ${prefix}.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        rdkit: stub
        pandas: stub
        pyarrow: stub
    END_VERSIONS
    """
}
