// modules/local/preprocess_candidates/main.nf

process PREPROCESS_CANDIDATES {
    debug true

    tag "${smi_gz}"
    label 'process_medium'

    container "lynceus/preprocess-candidates:0.1.0"

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
        polars: \$(python3 -c "import polars; print(polars.__version__)")
    END_VERSIONS
    """
}
