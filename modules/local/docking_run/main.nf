// modules/local/docking_run/main.nf

process DOCKING_RUN {
    label 'process_single'
    container 'lynceus/docking-run:0.1.0'

    input:
    path target
    path binding_sites
    path candidates

    script:
    """
    docking-run
    """
}
