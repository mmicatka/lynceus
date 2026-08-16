// modules/local/retrieve_candidates/main.nf

process RETRIEVE_CANDIDATES {
    tag "${uri_list}"

    container "quay.io/biocontainers/aria2:1.36.0"
    containerOptions '--entrypoint ""'

    input:
    path uri_list

    output:
    path "candidates/*", emit: candidates
    path "aria2c.log", emit: log

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: '--max-connection-per-server=4 --max-concurrent-downloads=8 --continue=true --retry-wait=5 --max-tries=3'
    """
    mkdir -p candidates

    aria2c \\
        --input-file=${uri_list} \\
        --dir=candidates \\
        --log=aria2c.log \\
        --log-level=info \\
        ${args}
    """
}
