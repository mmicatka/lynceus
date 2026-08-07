// modules/local/retrieve_candidates/main.nf

process RETRIEVE_CANDIDATES {
    tag "${uri_list}"

    container "quay.io/biocontainers/aria2:1.36.0"
    containerOptions '--entrypoint ""'

    publishDir "${params.outdir}/candidate/retrieve", mode: 'copy'

    input:
    path uri_list

    output:
    path "candidates/*", emit: candidates
    path "aria2c.log", emit: log
    path "versions.yml", emit: versions

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

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        aria2: \$(aria2c --version | head -n1 | sed 's/aria2 version //')
    END_VERSIONS
    """

    stub:
    """
    mkdir -p candidates
    touch candidates/stub_candidate.txt
    touch aria2c.log

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        aria2: stub
    END_VERSIONS
    """
}
