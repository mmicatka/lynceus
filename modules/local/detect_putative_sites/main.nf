// modules/local/detect_putative_sites/main.nf

process DETECT_PUTATIVE_SITES {
    debug true

    tag "${member_id}"

    input:
    tuple val(member_id), val(weight), path(structure)

    output:
    tuple val(member_id), path("${member_id}.sites.json"), emit: sites

    script:
    """
    python3 -m detect_putative_sites.detect_putative_sites \\
        --structure ${structure} \\
        --member-id ${member_id} \\
        --weight ${weight} \\
        --out ${member_id}.sites.json
    """
}
