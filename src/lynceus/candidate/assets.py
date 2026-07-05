# src/lynceus/candidate/assets.py

import dagster as dg

from lynceus.candidate.config import CandidateConfiguration


@dg.asset
def retrieve_candidates(context, config: CandidateConfiguration):
    context.log.info("Ingesting data with batch size: %d", config.batch_size)
