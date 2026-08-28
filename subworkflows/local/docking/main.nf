// subworkflows/local/docking/main.nf

include { DOCKING_RUN } from '../../../modules/local/docking_run'

workflow DOCKING {
    take:
    target_surfaces // tuple: ensemble_id, sites (path), prepped (path)
    candidates_done // sentinel: val true, emit: done — from SAMPLE_CANDIDATES
    candidates_path // val: s3://bucket/... path SAMPLE_CANDIDATES wrote to

    main:

    states_ch = target_surfaces.flatMap { _ensemble_id, _sites, prepped_dir ->
        prepped_dir
            .listFiles()
            .findAll { file -> file.name.endsWith('.pdbqt') }
            .collect { pdbqt ->
                def conformational_state_id = pdbqt.name.replaceAll(/\.pdbqt$/, '')
                tuple(conformational_state_id, pdbqt)
            }
    }

    sites_ch = target_surfaces
        .flatMap { _ensemble_id, sites_json, _prepped_dir -> sites_json }
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

    ch_candidates_path = candidates_done.collect().map { candidates_path }.first()

    DOCKING_RUN(docking_jobs_ch, ch_candidates_path)

    emit:
    results = DOCKING_RUN.out.results
}
