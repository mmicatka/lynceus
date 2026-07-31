// modules/local/docking_prep/main.nf

process DOCKING_PREP_TARGET {
    tag "${ensemble_id}"
    label 'process_single'
    container 'lynceus/docking-prep:0.1.0'

    input:
    tuple val(ensemble_id), path(ensemble_dir)

    output:
    path "${ensemble_id}_prepped", emit: prepped
    tuple val("${task.process}"), val('docking_prep'), eval("python3 -c 'import docking_prep; print(docking_prep.__version__)'"), emit: versions_docking_prep, topic: versions

    script:
    """
    docking-prepare-ensemble \\
        --ensemble ${ensemble_dir} \\
        --output ${ensemble_id}_prepped
    """
}

process DOCKING_PREP_CANDIDATE_CONFORMER_GENERATE {
    label 'process_single'
    container 'lynceus/docking-prep:0.1.0'

    input:
    path input_parquet

    output:
    path "${input_parquet.simpleName}_conformers/output.parquet", emit: conformers

    script:
    """
    conformer-generate \\
    --input ${input_parquet} \\
    --output ${input_parquet.baseName}_conformers
    """
}

process DOCKING_PREP_CANDIDATE_CONVERT_PDBQT {
    label 'process_single'
    container 'lynceus/docking-prep:0.1.0'

    input:
    path input_parquet

    output:
    path "${input_parquet.simpleName}_converted/output.parquet", emit: converted

    script:
    """
    convert-pdbqt \\
    --input ${input_parquet} \\
    --output ${input_parquet.baseName}_converted
    """
}
