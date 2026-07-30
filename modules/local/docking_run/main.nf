// modules/local/docking_run/main.nf

process DOCKING_RUN {
    label 'process_single'
    container 'lynceus/docking:0.1.0'

    input:
    path sites

    script:
    """
    docking-run 
    """
}
