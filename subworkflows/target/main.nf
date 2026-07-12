// subworkflows/target/main.nf

include { RETRIEVE_PDB } from '../../modules/local/retrieve_pdb/main'

workflow TARGET {
  take:
  config

  main:
  ch_versions = channel.empty()

  RETRIEVE_PDB()
}
