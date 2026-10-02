// workflows/lynceus.nf

include { CANDIDATES } from '../subworkflows/local/candidates'
include { TARGETS } from '../subworkflows/local/targets'
include { FILTER } from '../subworkflows/local/filter'


workflow LYNCEUS {
  CANDIDATES(params.candidates)
  ch_candidate_done = CANDIDATES.out.done

  TARGETS(params.target)
  ch_target_done = TARGETS.out.done

  FILTER(params.filter, ch_candidate_done, ch_target_done)
}
