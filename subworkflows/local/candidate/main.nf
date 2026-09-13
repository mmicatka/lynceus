// subworkflows/candidate/main.nf

include { COUNT_CANDIDATES ; MERGE_CANDIDATE_COUNTS ; ALLOCATE_CANDIDATE_SAMPLES ; SAMPLE_CANDIDATES ; SHARD_SAMPLES } from '../../../modules/local/rebalance_candidates'

workflow CANDIDATE {
  take:
  config

  main:
  bucket = config.bucket

  ch_source_keys = channel.fromList(config.sources)

  ch_candidate_sources = ch_source_keys.map { source_key ->
    "${config.source_prefix}/${source_key}"
  }

  COUNT_CANDIDATES(ch_candidate_sources, bucket)

  ch_count_keys = COUNT_CANDIDATES.out.count.collect()

  MERGE_CANDIDATE_COUNTS(ch_count_keys, bucket)

  ALLOCATE_CANDIDATE_SAMPLES(
    MERGE_CANDIDATE_COUNTS.out.counts_json,
    config.source_prefix,
    config.target_total,
    config.floor_per_folder,
    bucket,
  )

  ch_folder_allocations = ALLOCATE_CANDIDATE_SAMPLES.out.manifest_key
    .map { key -> file("s3://${bucket}/${key}") }
    .splitCsv(header: true)
    .map { row -> tuple(row.folder, row.source, row.target_count as Integer) }

  SAMPLE_CANDIDATES(ch_folder_allocations, config.candidate_samples_prefix, bucket)

  ch_all_samples_done = SAMPLE_CANDIDATES.out.done
    .collect()
    .map { true }
    .first()

  n_shards = Math.ceil(config.target_total / config.num_per_shard) as int
  sample_glob = "${config.candidate_samples_prefix.toString().replaceAll('/$', '')}/*_sample.parquet"

  SHARD_SAMPLES(
    ch_all_samples_done,
    sample_glob,
    n_shards,
    config.shard_output_prefix,
    bucket,
  )

  emit:
  candidate_counts = MERGE_CANDIDATE_COUNTS.out.counts_json
  allocation_manifest = ALLOCATE_CANDIDATE_SAMPLES.out.manifest_key
  shard_prefix = SHARD_SAMPLES.out.shard_prefix
  done = SHARD_SAMPLES.out.done
}
