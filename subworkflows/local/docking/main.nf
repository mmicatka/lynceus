// subworkflows/local/docking/main.nf

include { DOCKING_RUN } from '../../../modules/local/docking_run'

workflow DOCKING {
    take:
    target_surfaces // tuple: manifest (path), members (path), sites (path)
    candidates_done // sentinel: val true, emit: done
    candidates_key // val: S3 key of the sampled candidates parquet

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
            )
        }
    }

    ch_candidates_key = candidates_done.collect().map { true }.first().map { candidates_key }

    DOCKING_RUN(docking_jobs_ch, "lynceus", ch_candidates_key)

    emit:
    results = DOCKING_RUN.out.results
}
