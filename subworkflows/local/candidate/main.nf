// subworkflows/candidate/main.nf

include { COUNT_CANDIDATES } from '../../../modules/local/rebalance_candidates'

workflow CANDIDATE {
  take:
  config

  main:
  ch_sources_keys = channel.fromList(config.sources)
  bucket = config.bucket

  ch_candidate_sources = ch_sources_keys.map { source_key ->
    "${config.source_prefix}/raw/${source_key}"
  }

  COUNT_CANDIDATES(ch_candidate_sources, bucket)
}
