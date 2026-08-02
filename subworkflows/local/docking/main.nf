// subworkflows/local/docking/main.nf

include { DOCKING_PREP_TARGET ; DOCKING_PREP_CANDIDATE_CONFORMER_GENERATE ; DOCKING_PREP_CANDIDATE_CONVERT_PDBQT } from '../../../modules/local/docking_prep'
include { DETECT_PUTATIVE_BINDING_SITES } from '../../../modules/local/detect_putative_binding_sites'
include { DOCKING_RUN_CPU } from '../../../modules/local/docking_run'

workflow DOCKING {
    take:
    target_protein_conformational_ensemble // protein conformational ensemble
    candidates // path: candidate parquet

    main:

    // Prep
    DOCKING_PREP_TARGET(target_protein_conformational_ensemble)
    DETECT_PUTATIVE_BINDING_SITES(target_protein_conformational_ensemble)

    DOCKING_PREP_CANDIDATE_CONFORMER_GENERATE(candidates)
    DOCKING_PREP_CANDIDATE_CONVERT_PDBQT(DOCKING_PREP_CANDIDATE_CONFORMER_GENERATE.out.conformers)

    // Run docking
    states_ch = DOCKING_PREP_TARGET.out.prepped.flatMap { _ensemble_id, prepped_dir ->
        prepped_dir
            .listFiles()
            .findAll { file -> file.name.endsWith('.pdbqt') }
            .collect { pdbqt ->
                def conformational_state_id = pdbqt.name.replaceAll(/\.pdbqt$/, '')
                tuple(conformational_state_id, pdbqt)
            }
    }
    sites_ch = DETECT_PUTATIVE_BINDING_SITES.out.sites
        .splitJson()
        .map { site ->
            tuple(
                site.conformational_state_id,
                site.site_id,
                site.center,
                [site.extent.radius * 2] * 3,
            )
        }
    docking_jobs_ch = states_ch.combine(sites_ch, by: 0)
    DOCKING_RUN_CPU(docking_jobs_ch, DOCKING_PREP_CANDIDATE_CONVERT_PDBQT.out.converted)

    emit:
    results = DOCKING_RUN_CPU.out.results
}
