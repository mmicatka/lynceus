// modules/local/physiochemical_filter/main.nf


process PHYSIOCHEMICAL_FILTER {
    debug true

    container "lynceus/physiochemical-filter:0.1.0"

    publishDir "${params.outdir}/candidate/physiochemical_filter", mode: 'copy'

    input:
    path parquet_files, stageAs: 'input??/*'
    path filter_config
    val partition_size

    output:
    path "partitions/*.parquet", emit: parquet
    path "filter_report.json", emit: report
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    physiochemical-filter \\
        --input ${parquet_files} \\
        --config ${filter_config} \\
        --output-dir partitions \\
        --partition-size ${partition_size} \\
        --report filter_report.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        duckdb: \$(python3 -c "import duckdb; print(duckdb.__version__)")
    END_VERSIONS
    """

    stub:
    """
    mkdir -p partitions
    touch partitions/stub-00000.parquet
    touch filter_report.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        duckdb: stub
    END_VERSIONS
    """
}
