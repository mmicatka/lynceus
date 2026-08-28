// subworkflows/candidate/main.nf

include { PREPROCESS_CANDIDATES } from '../../../modules/local/preprocess_candidates'
include { PHYSIOCHEMICAL_FILTER } from '../../../modules/local/physiochemical_filter'
include { REBALANCE_CANDIDATES } from '../../../modules/local/rebalance_candidates'

workflow CANDIDATE {
  take:
  bucket
  num_per_shard
  filter_config

  main:
  directory = "s3://${bucket}/candidates"

  tranches = ["TEST"]

  def pattern = tranches.size() == 1
    ? "${directory}/raw/${tranches[0]}/*.smi.gz"
    : "${directory}/raw/{${tranches.join(',')}}/*.smi.gz"

  ch_smi_gz = channel.fromPath(pattern, checkIfExists: true)
    .map { f -> tuple(f.parent.name, f) }
    .filter { tranche, f ->
      def stem = f.name.replaceAll(/\.smi\.gz$/, '')
      def expected = file("${directory}/preprocessed/${tranche}/${stem}.parquet")
      !expected.exists()
    }

  PREPROCESS_CANDIDATES(ch_smi_gz, bucket)

  _ch_preprocess_done = PREPROCESS_CANDIDATES.out.done
    .collect()
    .ifEmpty { true }

  REBALANCE_CANDIDATES(
    _ch_preprocess_done.map { "${directory}/preprocessed/**/*.parquet" },
    "candidates/rebalanced",
    bucket,
    num_per_shard,
  )

  ch_rebalanced = REBALANCE_CANDIDATES.out.done.flatMap { file("${directory}/rebalanced/*.parquet") }

  PHYSIOCHEMICAL_FILTER(ch_rebalanced, filter_config, bucket)

  emit:
  done = PHYSIOCHEMICAL_FILTER.out.done
}
