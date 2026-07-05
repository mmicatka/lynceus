# src/lynceus/candidate/config.py

import dagster as dg


class CandidateConfiguration(dg.Config):
    batch_size: int
