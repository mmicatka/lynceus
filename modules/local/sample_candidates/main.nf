// modules/local/sample_candidates/main.nf

process SAMPLE_CANDIDATES {
    tag "sample_candidates"
    label 'process_single'
    container "lynceus/sample-candidates:0.1.0"

    input:
    path candidates_parquets, stageAs: 'candidates_*.parquet'
    val num_samples
    val seed

    output:
    path "candidates.parquet", emit: candidates
    tuple val("${task.process}"), val('python'), eval("python3 --version | sed 's/Python //g'"), emit: versions_python, topic: versions
    tuple val("${task.process}"), val('rdkit'), eval("python3 -c 'import rdkit; print(rdkit.__version__)'"), emit: versions_rdkit, topic: versions
    tuple val("${task.process}"), val('polars'), eval("python3 -c 'import polars; print(polars.__version__)'"), emit: versions_polars, topic: versions

    script:
    """
    sample-candidates \\
        --input-glob "candidates_*.parquet" \\
        --reservoir-size ${num_samples} \\
        --seed ${seed} \\
        --output candidates.parquet
    """

    stub:
    """
    touch candidates.parquet
    """
}
