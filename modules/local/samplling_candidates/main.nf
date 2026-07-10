// modules/local/sample_candidates/main.nf

process SAMPLE_CANDIDATES {
    tag "${meta.id}"
    label 'process_medium'

    // TODO: replace with the custom-built local image used by the other
    // Candidate subworkflow steps (preprocess.py's polars/RDKit image is
    // likely reusable here directly, since deps overlap: polars + rdkit).
    container 'lynceus/candidate-preprocess:latest'

    input:
    tuple val(meta), path(candidates_parquet, stageAs: 'candidates_*.parquet')

    output:
    tuple val(meta), path("${meta.id}.training_candidates.parquet"), emit: training_candidates
    path "versions.yml", emit: versions

    script:
    def args = task.ext.args ?: ''
    def reservoir_size = params.sample_candidates_reservoir_size ?: 25000
    def sample_size = params.sample_candidates_sample_size ?: 5000
    def cluster_cutoff = params.sample_candidates_cluster_cutoff ?: 0.4
    def smiles_col = params.sample_candidates_smiles_col ?: 'smiles'
    def id_col = params.sample_candidates_id_col ?: 'candidate_id'
    def weight_arg = params.sample_candidates_weight_col ? "--weight-col ${params.sample_candidates_weight_col}" : ''
    def prebin_arg = params.sample_candidates_prebin_max ? "--prebin-max ${params.sample_candidates_prebin_max}" : ''
    def skip_diversity_arg = params.sample_candidates_skip_diversity ? '--skip-diversity' : ''
    def seed = params.sample_candidates_seed ?: 42
    """
    sample_candidates.py \\
        --input-glob "candidates_*.parquet" \\
        --smiles-col ${smiles_col} \\
        --id-col ${id_col} \\
        --reservoir-size ${reservoir_size} \\
        --sample-size ${sample_size} \\
        --cluster-cutoff ${cluster_cutoff} \\
        --seed ${seed} \\
        ${weight_arg} \\
        ${prebin_arg} \\
        ${skip_diversity_arg} \\
        ${args} \\
        --output ${meta.id}.training_candidates.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python3 --version | sed 's/Python //g')
        rdkit: \$(python3 -c "import rdkit; print(rdkit.__version__)")
        polars: \$(python3 -c "import polars; print(polars.__version__)")
    END_VERSIONS
    """

    stub:
    """
    touch ${meta.id}.training_candidates.parquet
    touch versions.yml
    """
}
