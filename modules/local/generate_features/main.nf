// modules/local/feature_generation/main.nf

process FEATURE_GENERATION {
    container "${params.registry}/lynceus/feature-generation:0.1.0"

    label 'cpu_high'

    input:
    tuple val(input), val(output)
    val bucket

    script:
    """
    generate-features \\
        --input ${input} \\
        --output ${output} \\
        --use-blob-storage \\
        --bucket ${bucket} \\
        --features atom_pair \\
        --features autocorr \\
        --features descriptors \\
        --features ecfp \\
        --features functional_groups \\
        --features morse \\
        --features rdf \\
        --features topological_torsion \\
        --features usrcat \\
        --features whim \\
        --num-workers ${task.cpus}
    """
}
