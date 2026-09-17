// modules/local/feature_generation/main.nf

process FEATURE_GENERATION {
    container "${params.registry}/lynceus/feature-generation:0.1.0"

    label 'cpu_high'

    input:
    val bucket

    script:
    """
    """
}
