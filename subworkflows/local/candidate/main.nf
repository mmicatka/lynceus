// subworkflows/candidate/main.nf

include { PREPROCESS_CANDIDATES } from '../../../modules/local/preprocess_candidates'
include { PHYSIOCHEMICAL_FILTER } from '../../../modules/local/physiochemical_filter'
include { REBALANCE_CANDIDATES } from '../../../modules/local/rebalance_candidates'

workflow CANDIDATE {
  take:
  uri_list // path: file containing one s3:// URI per line
  filter_config // path: filter config
  num_shards // int

  main:
  ch_candidates = channel.fromPath(uri_list)
    .splitText { line -> line.trim() }
    .filter { line -> line }
    .map { uri -> file(uri) }

  ch_smi_gz = ch_candidates.filter { candidate_file -> candidate_file.name.endsWith('.smi.gz') }

  PREPROCESS_CANDIDATES(ch_smi_gz)

  ch_preprocess_done = PREPROCESS_CANDIDATES.out.done.collect()

  REBALANCE_CANDIDATES(
    ch_preprocess_done.map { "s3://${params.candidates.output_bucket}/preprocessed" },
    ch_preprocess_done.map { "s3://${params.candidates.output_bucket}/rebalanced" },
    num_shards,
  )

  ch_shards = REBALANCE_CANDIDATES.out.done.flatMap { _shard -> file("s3://${params.candidates.output_bucket}/rebalanced/shard_*.parquet") }

  PHYSIOCHEMICAL_FILTER(ch_shards, filter_config)
}
