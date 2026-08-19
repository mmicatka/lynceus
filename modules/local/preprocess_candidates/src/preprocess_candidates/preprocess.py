# modules/local/preprocess_candidates/src/preprocess_candidates/preprocess.py

from .steps import DescriptorsStep, PainsStep, Step

DEFAULT_PIPELINE_STEPS: list[Step] = [
    DescriptorsStep(),
    PainsStep(),
    # MorganFingerprintStep(radius=2, n_bits=2048),
    # ConformerGenerateStep(random_seed=1000),
]
