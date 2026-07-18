// subworkflows/local/docking/main.nf

include { DOCKING_PREP } from './prep.nf'

workflow DOCKING {
  take:
  target // target pce
  putative_binding_sites // putative binding sites json
  candidates // path: filtered + repartitioned candidate parquets
  chunk_size // val: rows per candidate chunk

  main:
  ch_versions = channel.empty()

  // prep targets
  DOCKING_PREP(target, putative_binding_sites, candidates, chunk_size)

  emit:
  versions = ch_versions
}
