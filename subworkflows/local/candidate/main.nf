// subworkflows/candidate/main.nf

include { COUNT_CANDIDATES ; MERGE_CANDIDATE_COUNTS ; ALLOCATE_CANDIDATE_SAMPLES ; SAMPLE_CANDIDATES ; SHARD_SAMPLES } from '../../../modules/local/rebalance_candidates'
include { GENERATE_CONFORMERS } from '../../../modules/local/generate_conformers'


workflow CANDIDATES {
  take:
  config

  main:
  _REBALANCE_CANDIDATES(
    config
  )
}

// workflow CANDIDATES {
//   take:
//   config

//   main:
//   _REBALANCE_CANDIDATES(
//     config
//   )

//   ch_shards = _REBALANCE_CANDIDATES.out.shard_manifest
//     .map { key -> file("s3://${config.bucket}/${key}") }
//     .splitText()
//     .map { line -> new groovy.json.JsonSlurper().parseText(line.trim()) }
//     .map { row ->
//       def input_key = row.output_path.replaceFirst("^s3://${config.bucket}/", "")
//       def output_key = "${config.conformers_output_prefix}/shard_${row.shard_id}_conformers.parquet"
//       return tuple(input_key, output_key)
//     }

//   GENERATE_CONFORMERS(
//     ch_shards,
//     config.bucket,
//   )

//   emit:
//   candidate_counts = _REBALANCE_CANDIDATES.out.candidate_counts
//   allocation_manifest = _REBALANCE_CANDIDATES.out.allocation_manifest
//   conformers_done = GENERATE_CONFORMERS.out.done.collect()
// }

workflow _REBALANCE_CANDIDATES {
  take:
  config

  main:
  bucket = config.bucket

  ch_source_keys = channel.fromList(config.sources)

  ch_candidate_sources = ch_source_keys.map { source_key ->
    "${config.source_prefix}/${source_key}"
  }

  COUNT_CANDIDATES(ch_candidate_sources, config.parquet_prefix, bucket)

  ch_count_keys = COUNT_CANDIDATES.out.count.collect()

  MERGE_CANDIDATE_COUNTS(ch_count_keys, bucket)

  ALLOCATE_CANDIDATE_SAMPLES(
    MERGE_CANDIDATE_COUNTS.out.counts_json,
    config.source_prefix,
    config.target_total,
    config.floor_per_source,
    bucket,
  )

  ch_parquet_dirs = COUNT_CANDIDATES.out.parquet.map { parquet_key -> tuple(parquet_key.tokenize('/').last(), parquet_key) }

  ch_source_allocations = ALLOCATE_CANDIDATE_SAMPLES.out.manifest_key
    .map { key -> file("s3://${bucket}/${key}") }
    .splitCsv(header: true)
    .map { row ->
      tuple(row.folder, row.target_count as Long, row.source_count as Long)
    }
    .combine(ch_parquet_dirs, by: 0)
    .map { folder, target_count, source_count, parquet_dir ->
      tuple(folder, parquet_dir, target_count, source_count)
    }

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
  shard_manifest = SHARD_SAMPLES.out.shard_manifest
}
