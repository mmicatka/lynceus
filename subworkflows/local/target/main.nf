// subworkflows/target/main.nf

include { RETRIEVE_PDB } from '../../../modules/local/retrieve_pdb'
include { GENERATE_MANIFEST } from '../../../modules/local/generate_manifest'

workflow TARGET {
  take:
  config

  main:
  def pdb_ids = config.components.collect { component -> component.pdb_id }

  ch_retrieve_input = channel.of(
    tuple(config.ensemble_id, pdb_ids)
  )

  RETRIEVE_PDB(ch_retrieve_input)
  GENERATE_MANIFEST(RETRIEVE_PDB.out.structure_dir)

  emit:
  protein_conformational_ensemble = GENERATE_MANIFEST.out.protein_conformational_ensemble
}
