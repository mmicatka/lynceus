// subworkflows/candidate/main.nf

include { PREPROCESS_CANDIDATES } from '../../../modules/local/preprocess_candidates'
include { PHYSIOCHEMICAL_FILTER } from '../../../modules/local/physiochemical_filter'
include { REBALANCE_CANDIDATES } from '../../../modules/local/rebalance_candidates'

workflow CANDIDATE {
  take:
  config

  main:
  directory = "s3://${config.bucket}/candidates"

  tranches = config.tranches

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

  PREPROCESS_CANDIDATES(ch_smi_gz, config.bucket)

  _ch_preprocess_done = PREPROCESS_CANDIDATES.out.done
    .collect()
    .ifEmpty { true }

  REBALANCE_CANDIDATES(
    _ch_preprocess_done.map { "${directory}/preprocessed/**/*.parquet" },
    "candidates/rebalanced",
    config.bucket,
    config.num_per_shard,
  )

  ch_rebalanced = REBALANCE_CANDIDATES.out.done
    .flatMap { files("${directory}/rebalanced/*.parquet") }
    .map { f -> "${directory}/rebalanced/${f.name}" }

  PHYSIOCHEMICAL_FILTER(ch_rebalanced, config.filter_config, config.bucket)

  emit:
  done = PHYSIOCHEMICAL_FILTER.out.done
}
