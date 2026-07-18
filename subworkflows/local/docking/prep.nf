// subworkflows/local/docking/prep.nf

include { GENERATE_DOCKING_BOXES } from '../../../modules/local/generate_docking_boxes'
include { PREPARE_DOCKING_TARGET } from '../../../modules/local/prepare_docking_target'

include { SPLIT_CANDIDATES } from '../../../modules/local/split_candidates'
include { PREPARE_DOCKING_CANDIDATES } from '../../../modules/local/prepare_docking_candidates'

workflow DOCKING_PREP {
  take:
  target // target pce
  putative_binding_sites // putative binding sites json
  candidates // path: candidate parquet
  chunk_size // val: rows per candidate chunk

  main:
  ch_versions = channel.empty()

  GENERATE_DOCKING_BOXES(putative_binding_sites)
  ch_versions = ch_versions.mix(GENERATE_DOCKING_BOXES.out.versions)

  ch_receptor_input = putative_binding_sites
    .map { conformational_state_id, _sites_json -> conformational_state_id }
    .combine(target)

  PREPARE_DOCKING_TARGET(ch_receptor_input)
  ch_versions = ch_versions.mix(PREPARE_DOCKING_TARGET.out.versions)

  // Candidate Prep
  ch_split_input = candidates.map { meta, parquet -> tuple(meta, parquet, chunk_size) }
  SPLIT_CANDIDATES(ch_split_input)
  ch_versions = ch_versions.mix(SPLIT_CANDIDATES.out.versions)

  ch_candidate_chunks = SPLIT_CANDIDATES.out.chunks.flatMap { meta, chunk_files -> chunk_files.collect { chunk_file -> tuple(meta, chunk_file) } }

  PREPARE_DOCKING_CANDIDATES(ch_candidate_chunks)
  ch_versions = ch_versions.mix(PREPARE_DOCKING_CANDIDATES.out.versions)

  emit:
  docking_boxes = GENERATE_DOCKING_BOXES.out.boxes // [ val(conformational_state_id), path(boxes_json) ]
  receptor_pdbqt = PREPARE_DOCKING_TARGET.out.pdbqt // [ val(conformational_state_id), path(receptor.pdbqt) ]
  ligand_pdbqt_dirs = PREPARE_DOCKING_CANDIDATES.out.prepared // [ val(meta), path(pdbqt_dir), path(prep_manifest.parquet) ]
  versions = ch_versions
}
