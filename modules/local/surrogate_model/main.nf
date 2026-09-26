// modules/local/surrogate_model/main.nf


process SAMPLE_SURROGATE_CANDIDATES {
    container "${params.registry}/lynceus/surrogate-model:0.1.0"

    label 'cpu_medium'
    label 'pvc_io_retry'

    input:
    tuple val(features_glob), val(output)
    val bucket
    val model_key
    val top_k
    val uniform_k

    output:
    val output, emit: selected_ids
    val true, emit: done

    script:
    if (model_key && !top_k) {
        error("SAMPLE_SURROGATE_CANDIDATES: 'top_k' is required when 'model_key' is set")
    }
    if (!model_key && top_k) {
        error(
            "SAMPLE_SURROGATE_CANDIDATES: 'top_k' has no effect without 'model_key'; unset top_k for a uniform-only round"
        )
    }

    def model_args = model_key ? "--model-path ${model_key} --top-k ${top_k}" : ""
    """
    sample-surrogate-candidates \\
        --features-glob ${features_glob} \\
        --output ${output} \\
        --uniform-k ${uniform_k} \\
        ${model_args} \\
        --use-blob-storage \\
        --bucket ${bucket} \\
    """
}
