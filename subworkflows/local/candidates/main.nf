// subworkflows/candidates/main.nf

include { COUNT_CANDIDATES ; MERGE_CANDIDATE_COUNTS ; ALLOCATE_CANDIDATE_SAMPLES ; SAMPLE_CANDIDATES ; SHARD_SAMPLES } from '../../../modules/local/rebalance_candidates'
include { GENERATE_CONFORMERS } from '../../../modules/local/generate_conformers'


workflow CANDIDATES {
  take:
  config

  main:
  _REBALANCE_CANDIDATES(
    config
  )

  bucket = config.bucket

  ch_shards = _REBALANCE_CANDIDATES.out.shard_manifest
    .map { key -> bucket ? file("s3://${bucket}/${key}") : file(key) }
    .splitText()
    .map { line -> new groovy.json.JsonSlurper().parseText(line.trim()) }
    .map { row ->
      def s3_prefix = "s3://${bucket}/"
      def input_key = bucket && row.output_path.startsWith(s3_prefix)
        ? row.output_path.replaceFirst("^${s3_prefix}", "")
        : row.output_path
      def output_key = "${config.conformers_output_prefix}/shard_${row.shard_id}.parquet"
      return tuple(input_key, output_key)
    }

  GENERATE_CONFORMERS(
    ch_shards,
    bucket,
  )

  emit:
  done = GENERATE_CONFORMERS.out.done.collect()
}

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

  ch_parquet_prefix_ready = COUNT_CANDIDATES.out.done
    .collect()
    .map { config.parquet_prefix }

  MERGE_CANDIDATE_COUNTS(ch_parquet_prefix_ready, bucket)

  ALLOCATE_CANDIDATE_SAMPLES(
    MERGE_CANDIDATE_COUNTS.out.counts_json,
    config.source_prefix,
    config.target_total,
    config.floor_per_source,
    bucket,
  )

  ch_source_allocations = ALLOCATE_CANDIDATE_SAMPLES.out.manifest_key
    .map { key -> bucket ? file("s3://${bucket}/${key}") : file(key) }
    .splitCsv(header: true)
    .map { row ->
      def parquet_dir = "${config.parquet_prefix}/${row.folder}"
      tuple(row.folder, parquet_dir, row.target_count as Long, row.source_count as Long)
    }

  SAMPLE_CANDIDATES(ch_source_allocations, config.candidate_samples_prefix, bucket)

  sample_glob = "${config.candidate_samples_prefix.toString().replaceAll('/$', '')}/*.parquet"

  ch_sample_glob_ready = SAMPLE_CANDIDATES.out.done
    .collect()
    .map { sample_glob }

  SHARD_SAMPLES(
    ch_sample_glob_ready,
    config.candidates_per_shard,
    config.shard_output_prefix,
    bucket,
  )

  emit:
  candidate_counts = MERGE_CANDIDATE_COUNTS.out.counts_json
  allocation_manifest = ALLOCATE_CANDIDATE_SAMPLES.out.manifest_key
  shard_manifest = SHARD_SAMPLES.out.shard_manifest
}
