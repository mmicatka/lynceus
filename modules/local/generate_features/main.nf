// modules/local/generate_features/main.nf

process GENERATE_FEATURES {
    container "${params.registry}/lynceus/generate-features:0.1.0"

    label 'cpu_medium'

    input:
    tuple val(input), val(output)
    val bucket
    val features

    output:
    val true, emit: done

    script:
    if (!features) {
        error("GENERATE_FEATURES: 'features' list must not be empty")
    }
    def features_args = features.collect { feature -> "--features ${feature}" }.join(' ')
    """
    generate-features \\
        --input ${input} \\
        --output ${output} \\
        --use-blob-storage \\
        --bucket ${bucket} \\
        ${features_args} \\
        --num-workers ${task.cpus}
    """
}
