// subworkflows/target/main.nf

include { RETRIEVE_PDB } from '../../../modules/local/retrieve_pdb'
include { GENERATE_MANIFEST } from '../../../modules/local/generate_manifest'
include { DETECT_PUTATIVE_SITES } from '../../../modules/local/detect_putative_sites'


workflow TARGET {
  take:
  config

  main:
  ch_versions = channel.empty()

  def pdb_ids = config.components.collect { component -> component.pdb_id }

  ch_retrieve_input = channel.of(
    tuple(config.ensemble_id, pdb_ids)
  )

  RETRIEVE_PDB(ch_retrieve_input)
  ch_versions = ch_versions.mix(RETRIEVE_PDB.out.versions)

  GENERATE_MANIFEST(RETRIEVE_PDB.out.structure_dir)

  DETECT_PUTATIVE_SITES(GENERATE_MANIFEST.out.pce_package)

  emit:
  structure_dir = RETRIEVE_PDB.out.structure_dir
  versions = ch_versions
}
