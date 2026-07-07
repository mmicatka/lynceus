// workflows/lynceus.nf

include { CANDIDATE } from '../subworkflows/candidate/main'

workflow LYNCEUS {

  main:
  ch_versions = channel.empty()

  ch_uri_list = channel.fromPath(params.uri_list, checkIfExists: true)

  CANDIDATE(ch_uri_list)
  ch_versions = ch_versions.mix(CANDIDATE.out.versions)

  emit:
  candidates = CANDIDATE.out.candidates
  versions = ch_versions
}
