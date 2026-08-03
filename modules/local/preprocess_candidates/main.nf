// modules/local/preprocess_candidates/main.nf

process PREPROCESS_CANDIDATES {
    debug true

    label 'process_medium'

    container "lynceus/lynceus-chem:0.1.0"

    input:
    path smi_gz

    output:
    path "*.parquet", emit: parquet

    when:
    task.ext.when == null || task.ext.when

    script:
    def prefix = smi_gz.simpleName
    // strips both .gz and .smi (multi-extension aware)
    """
    lynceus-chem-preprocess \\
        --input ${smi_gz} \\
        --output ${prefix}.parquet
    """
}
