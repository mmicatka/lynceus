// subworkflows/local/docking/main.nf
include { DOCKING_RUN } from '../../../modules/local/docking_run'

workflow DOCKING {
    take:
    target_surfaces // tuple: manifest (path), members (path), sites (path) — from TARGET.out.target_surfaces
    candidates_done // sentinel: val true, emit: done — from SAMPLE_CANDIDATES
    candidates_path // val: s3://bucket/... path SAMPLE_CANDIDATES wrote to

    main:

    docking_jobs_ch = target_surfaces.flatMap { manifest, members, sites_json ->
        def sites = new groovy.json.JsonSlurper().parse(sites_json.toFile())
        sites.collect { site ->
            tuple(
                site.conformational_state_id,
                manifest,
                members,
                site.site_id,
                site.center,
                [site.extent.radius * 2] * 3,
            )
        }
    }

    ch_candidates_path = candidates_done.collect().map { file(candidates_path) }

    DOCKING_RUN(docking_jobs_ch, ch_candidates_path)

    emit:
    results = DOCKING_RUN.out.results
}
