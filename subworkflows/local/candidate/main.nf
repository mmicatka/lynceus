// subworkflows/candidate/main.nf

include { PREPROCESS_CANDIDATES } from '../../../modules/local/preprocess_candidates'
include { PHYSIOCHEMICAL_FILTER } from '../../../modules/local/physiochemical_filter'
include { REBALANCE_CANDIDATES } from '../../../modules/local/rebalance_candidates'

workflow CANDIDATE {
  take:
  bucket
  num_per_shard
  _filter_config

  main:
  directory = "s3://${bucket}/candidates"

  tranches = "0*,10,11"

  ch_smi_gz = channel.fromPath("${directory}/raw/H{${tranches}}/*.smi.gz")
    .map { f -> tuple(f.parent.name, f) }
    .filter { tranche, f ->
      def stem = f.name.replaceAll(/\.smi\.gz$/, '')
      def expected = file("${directory}/preprocessed/${tranche}/${stem}.parquet")
      !expected.exists()
    }

  PREPROCESS_CANDIDATES(ch_smi_gz, bucket)

  _ch_preprocess_done = PREPROCESS_CANDIDATES.out.done.collect()

  REBALANCE_CANDIDATES(
    "${directory}/preprocessed/**/*.parquet",
    "candidates/rebalanced",
    bucket,
    num_per_shard,
  )
}
