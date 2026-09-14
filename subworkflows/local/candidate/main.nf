// subworkflows/candidate/main.nf

include { COUNT_CANDIDATES ; MERGE_CANDIDATE_COUNTS ; ALLOCATE_CANDIDATE_SAMPLES ; SAMPLE_CANDIDATES ; SHARD_SAMPLES ; RESOLVE_PENDING_CANDIDATE_FOLDERS } from '../../../modules/local/rebalance_candidates'

workflow _REBALANCE_CANDIDATES {
  take:
  config

  main:
  bucket = config.bucket

  ch_source_keys = channel.fromList(config.sources)

  ch_candidate_sources = ch_source_keys.map { source_key ->
    "${config.source_prefix}/${source_key}"
  }

  RESOLVE_PENDING_CANDIDATE_FOLDERS(
    ch_candidate_sources.collect(),
    "_count.json",
    config.source_prefix,
    bucket,
  )

  ch_pending_count_sources = RESOLVE_PENDING_CANDIDATE_FOLDERS.out.pending_key
    .map { key -> file("s3://${bucket}/${key}") }
    .splitJson()
    .flatten()

  COUNT_CANDIDATES(ch_pending_count_sources, bucket)

  ch_count_keys = COUNT_CANDIDATES.out.count.collect()

  MERGE_CANDIDATE_COUNTS(ch_count_keys, bucket)

  ALLOCATE_CANDIDATE_SAMPLES(
    MERGE_CANDIDATE_COUNTS.out.counts_json,
    config.source_prefix,
    config.target_total,
    config.floor_per_source,
    bucket,
  )

  ch_source_allocations = ALLOCATE_CANDIDATE_SAMPLES.out.manifest_key
    .map { key -> file("s3://${bucket}/${key}") }
    .splitCsv(header: true)
    .map { row -> tuple(row.folder, row.source, row.target_count as Integer) }

  SAMPLE_CANDIDATES(ch_source_allocations, config.candidate_samples_prefix, bucket)

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

workflow CANDIDATES {
  take:
  config

  main:
  _REBALANCE_CANDIDATES(
    config
  )
}
