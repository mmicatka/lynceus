// subworkflows/candidate/main.nf

include { PREPROCESS_CANDIDATES } from '../../../modules/local/preprocess_candidates'

workflow CANDIDATE {
  take:
  uri_list // path: file containing one s3:// URI per line

  main:
  ch_candidates = channel.fromPath(uri_list)
    .splitText { line -> line.trim() }
    .filter { line -> line }
    .map { uri -> file(uri) }

  ch_smi_gz = ch_candidates.filter { candidate_file -> candidate_file.name.endsWith('.smi.gz') }

  PREPROCESS_CANDIDATES(ch_smi_gz)

  emit:
  processed = PREPROCESS_CANDIDATES.out.processed
}
