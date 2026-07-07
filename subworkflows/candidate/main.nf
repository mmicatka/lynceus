// subworkflows/candidate/main.nf

include { RETRIEVE_CANDIDATES } from '../../modules/local/retrieve_candidates/main'

workflow CANDIDATE {
  take:
  uri_list // path: file containing one download URI per line

  main:
  ch_versions = channel.empty()

  RETRIEVE_CANDIDATES(uri_list)
  ch_versions = ch_versions.mix(RETRIEVE_CANDIDATES.out.versions)

  emit:
  candidates = RETRIEVE_CANDIDATES.out.candidates // path: downloaded candidate files
  download_log = RETRIEVE_CANDIDATES.out.log // path: aria2c.log
  versions = ch_versions // channel: [ versions.yml ]
}
