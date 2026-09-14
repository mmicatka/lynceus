// modules/local/generate_conformers/main.nf

process GENERATE_CONFORMERS {
    container "${params.registry}/lynceus/generate-conformers:0.1.0"

    label 'process_high'
    label 'pvc_io_retry'

    input:
    tuple val(input), val(output)
    val bucket

    output:
    val true, emit: done

    script:
    """
    generate-conformers \\
        --input ${input} \\
        --output ${output} \\
        --use-blob-storage \\
        --bucket ${bucket} \\
        --num-workers ${task.cpus}
    """
}
