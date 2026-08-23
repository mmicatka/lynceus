// subworkflows/candidate/main.nf

include { PREPROCESS_CANDIDATES } from '../../../modules/local/preprocess_candidates'
include { PHYSIOCHEMICAL_FILTER } from '../../../modules/local/physiochemical_filter'
include { REBALANCE_CANDIDATES } from '../../../modules/local/rebalance_candidates'

workflow CANDIDATE {
  take:
  bucket // bucket name
  num_per_shard // int
  _filter_config // path: filter config

  main:
  directory = "s3://${bucket}/candidates"

  ch_smi_gz = channel.fromPath("${directory}/raw/H0*/*.smi.gz")
    .map { f -> tuple(f.parent.name, f) }

  PREPROCESS_CANDIDATES(ch_smi_gz, bucket)

  ch_preprocess_done = PREPROCESS_CANDIDATES.out.done.collect()

  REBALANCE_CANDIDATES(
    ch_preprocess_done.map { "${directory}/preprocessed/H0*/*.parquet" },
    "${directory}/rebalanced",
    bucket,
    num_per_shard,
  )

  // ch_shards = REBALANCE_CANDIDATES.out.done.flatMap { _shard -> file("s3://${params.candidates.output_bucket}/rebalanced/shard_*.parquet") }

  // PHYSIOCHEMICAL_FILTER(ch_shards, filter_config)
  ch_preprocess_done = PREPROCESS_CANDIDATES.out.done.collect()
}
