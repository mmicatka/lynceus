// subworkflows/candidates/main.nf

include { LOAD_CANDIDATES ; MERGE_CANDIDATE_COUNTS ; ALLOCATE_CANDIDATE_SAMPLES ; SAMPLE_CANDIDATES ; SHARD_CANDIDATES ; CONCAT_CANDIDATE_SHARDS } from '../../../modules/local/rebalance_candidates'
include { GENERATE_CONFORMERS } from '../../../modules/local/generate_conformers'


def resolveUri(bucket: String, key: String) {
  bucket ? "s3://${bucket}/${key}" : key
}

def toShardTuple(shardPath: Path, config: Map, bucket: String) {
  def shardId = "${shardPath.parent.name}_${shardPath.baseName}"
  def inputKey = bucket
    ? shardPath.toString().replaceFirst("^s3://${bucket}/", "")
    : shardPath.toString()
  def outputKey = "${config.conformers_output_prefix}/shard_${shardId}.parquet"
  tuple(inputKey, outputKey)
}

workflow CANDIDATES {
  take:
  config

  main:
  _REBALANCE_CANDIDATES(config)

  bucket = config.bucket
  shardGlob = resolveUri(bucket, "${config.shard_output_prefix}/*.parquet")

  ch_shards = _REBALANCE_CANDIDATES.out.concat_done
    .flatMap { files(shardGlob) }
    .map { shardPath -> toShardTuple(shardPath, config, bucket) }

  GENERATE_CONFORMERS(ch_shards, bucket)

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

  ch_shard_inputs = ch_source_allocations
    .map { folder, _parquet_dir, sample_dir, _target_count, _source_count ->
      tuple(folder, sample_dir)
    }
    .combine(SAMPLE_CANDIDATES.out.done.collect().map { true })
    .map { _folder, sample_dir, _ready ->
      tuple(sample_dir, config.shard_staging_prefix)
    }

  SHARD_CANDIDATES(ch_shard_inputs, config.num_shards, bucket)

  ch_concat_inputs = channel.fromList((0..<config.num_shards).toList())
    .combine(SHARD_CANDIDATES.out.done.collect().map { true })
    .map { shard_id, _ready ->
      tuple(
        "${config.shard_staging_prefix}/shard_id=${shard_id}/*.parquet",
        "${config.shard_output_prefix}/shard_${shard_id}.parquet",
      )
    }

  CONCAT_CANDIDATE_SHARDS(ch_concat_inputs, bucket)

  emit:
  candidate_counts = MERGE_CANDIDATE_COUNTS.out.counts_json
  allocation_manifest = ALLOCATE_CANDIDATE_SAMPLES.out.manifest_key
  concat_done = CONCAT_CANDIDATE_SHARDS.out.done.collect()
}
