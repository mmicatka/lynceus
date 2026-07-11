// modules/local/sample_candidates/main.nf

process SAMPLE_CANDIDATES {

    container "lynceus/sample:0.1.0"

    input:
    path candidates_parquet, stageAs: 'candidates_*.parquet'

    output:
    path ("training_candidates.parquet"), emit: training_candidates
    path "versions.yml", emit: versions

    script:
    """
    python3 -m src.sample_candidates \\
        --input-glob "candidates_*.parquet" \\
        --reservoir-size 20000 \\
        --seed 1000 \\
        --output training_candidates.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python3 --version | sed 's/Python //g')
        rdkit: \$(python3 -c "import rdkit; print(rdkit.__version__)")
        polars: \$(python3 -c "import polars; print(polars.__version__)")
    END_VERSIONS
    """

    stub:
    """
    touch training_candidates.parquet
    touch versions.yml
    """
}
