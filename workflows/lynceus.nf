// workflows/lynceus.nf

include { CANDIDATE } from '../subworkflows/local/candidate'

workflow LYNCEUS {
  ch_uri_list = file(params.candidates.uri_list, checkIfExists: true)

  CANDIDATE(ch_uri_list)
  CANDIDATE.out.processed.view { parquet_file -> "processed: ${parquet_file}" }
}
