// subworkflows/candidates/main.nf

include { LOAD_CANDIDATES ; MERGE_CANDIDATE_COUNTS ; ALLOCATE_CANDIDATE_SAMPLES ; SAMPLE_CANDIDATES ; SHARD_CANDIDATES ; CONCAT_CANDIDATE_SHARDS } from '../../../modules/local/rebalance_candidates'
include { GENERATE_CONFORMERS } from '../../../modules/local/generate_conformers'


workflow CANDIDATES {
  take:
  config

  main:
  _REBALANCE_CANDIDATES(
    config
  )

  bucket = config.bucket

  ch_shards = _REBALANCE_CANDIDATES.out.concat_done
    .map { file("${bucket ? "s3://${bucket}/" : ''}${config.shard_output_prefix}/*/*.parquet") }
    .flatMap { pattern -> file(pattern) }
    .map { shard_path ->
      def folder = shard_path.parent.name
      def shard_id = "${folder}_${shard_path.baseName}"
      def input_key = bucket
        ? shard_path.toString().replaceFirst("^s3://${bucket}/", "")
        : shard_path.toString()
      def output_key = "${config.conformers_output_prefix}/${shard_id}.parquet"
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

  LOAD_CANDIDATES(
    ch_candidate_sources,
    config.parquet_prefix,
    config.initial_shard_size_bytes,
    bucket,
  )

  ch_parquet_prefix_ready = LOAD_CANDIDATES.out.done
    .collect()
    .map { config.parquet_prefix }

  MERGE_CANDIDATE_COUNTS(ch_parquet_prefix_ready, bucket)

  ALLOCATE_CANDIDATE_SAMPLES(
    MERGE_CANDIDATE_COUNTS.out.counts_json,
    config.source_prefix,
    config.target_total,
    config.floor_per_source,
    config.allocation_path,
    bucket,
  )

  ch_source_allocations = ALLOCATE_CANDIDATE_SAMPLES.out.manifest_key
    .map { key -> bucket ? file("s3://${bucket}/${key}") : file(key) }
    .splitCsv(header: true)
    .map { row ->
      def parquet_dir = "${config.parquet_prefix}/${row.folder}"
      def sample_dir = "${config.candidate_samples_prefix}/${row.folder}"
      tuple(row.folder, parquet_dir, sample_dir, row.target_count as Long, row.source_count as Long)
    }

  ch_sample_inputs = ch_source_allocations.map { _folder, parquet_dir, sample_dir, target_count, source_count ->
    tuple(parquet_dir, sample_dir, source_count, target_count)
  }

  SAMPLE_CANDIDATES(ch_sample_inputs, config.initial_shard_size_bytes, bucket)

  ch_folders_for_sharding = ch_source_allocations.map { folder, _parquet_dir, sample_dir, _target_count, _source_count ->
    tuple(folder, sample_dir)
  }

  ch_samples_ready = SAMPLE_CANDIDATES.out.done.collect().map { true }.first()

  ch_shard_inputs = ch_folders_for_sharding
    .combine(ch_samples_ready)
    .map { folder, sample_dir, _ready ->
      def shard_dir = "${config.shard_output_prefix}/${folder}"
      tuple(sample_dir, shard_dir)
    }

  SHARD_CANDIDATES(ch_shard_inputs, config.num_shards, bucket)

  ch_shard_dirs = ch_shard_inputs.map { _sample_dir, shard_dir -> shard_dir }

  ch_shards_ready = SHARD_CANDIDATES.out.done.collect().map { true }.first()

  ch_concat_inputs = ch_shard_dirs
    .combine(ch_shards_ready)
    .map { shard_dir, _ready -> tuple(shard_dir, shard_dir) }

  CONCAT_CANDIDATE_SHARDS(ch_concat_inputs, bucket)

  emit:
  candidate_counts = MERGE_CANDIDATE_COUNTS.out.counts_json
  allocation_manifest = ALLOCATE_CANDIDATE_SAMPLES.out.manifest_key
  concat_done = CONCAT_CANDIDATE_SHARDS.out.done.collect()
}
