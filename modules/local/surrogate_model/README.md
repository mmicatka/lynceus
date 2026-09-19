# Surrogate Model

Goal: reduce an ultra-large library (1B+) to ~0.1% of it for docking against one protein + pocket, using surrogate models trained on docking labels.

## Invariants

- **One cascade per (protein, pocket, docking protocol).** Nothing crosses targets: hyperparameters, feature-view choices, and training samples are all independent.
- **Shared feature store: immutable, versioned, a function of the compound only.** Each run pins a store version (library snapshot, RDKit version, embedding checkpoint). New views are new versions, never mutations.
- **The surrogate is a filter, not a scorer.** It is judged only on concentrating the true top of the library into the final selection.
- **Docking protocol is frozen before modeling** (engine, receptor prep, box, ligand prep, scoring settings) and hashed into the target manifest. Changing it invalidates the models.

## Feature Store

Precomputed once, reused across targets, so amortized cost is not a constraint. Each target selects which views to consume.

| View | Role |
| --- | --- |
| Morgan fingerprint (counts, compact radius) | Strong baseline in every study |
| Atom-pair fingerprint | Complements compact-radius Morgan |
| RDKit physicochemical descriptors | Largest single gain on the hard pocket |
| Pretrained molecular LM embedding | Dense, no sparsity issues |
| Optional pretrained GNN embedding | Different inductive bias |

Bit-pack fingerprints, store embeddings at reduced precision, use a columnar format sharded by compound ID. No per-target embedding fine-tuning (forces re-embedding the library, defeats amortization).

## Success Definition

- The final selection is ~0.1% of the library, so if the label boundary is the top 1%, the library holds ~10x more actives than the selection can hold. "Recover the top 1%" is the wrong claim.
- Primary metric: **recall of an elite set (a small fraction of the top 0.1%) at the final selection size**, plus enrichment (fraction of the selection that is truly top-1%).
- The recall target R is set in advance and drives stage sizes and docking allocation. **Fix it first.**

## Sampling and Training

### Stage A: Initial random sample

- **100k compounds**, uniform random from the physchem-filtered library, seeded per target.
- Record docking failures explicitly; never drop them silently.
- Freeze the active threshold at the **1st percentile** of these scores (avoids concept drift).
- Carve pure-random calibration and test holdouts before any modeling; never used for training or acquisition.

### Stage B: Random evaluation set

- **~100k to 200k additional random compounds**, docked only for evaluation and threshold re-estimation on a larger unbiased sample.
- Needed because a 100k holdout has too few elite compounds to estimate elite recall. If cost forces a smaller set, define the evaluation elite more loosely and treat the tightest recall as an extrapolation.

### Stage C: Active sampling

- **5 to 10 rounds of 100k**, stopping when holdout elite recall plateaus (5 may suffice).
- Per-round mix: ~50-60% uncertainty (near boundary, ensemble disagreement), ~30-40% exploitation (highest predicted active probability), ~10% uniform random (guards against the model narrowing its own view).
- Later rounds sample from earlier stages' survivors, not the raw library.
- Acquired compounds augment training only. Calibration and test stay pure random.

| Cascade stage | Share of active-sampling budget (first guess, tune in pilot) |
| --- | --- |
| S1 (broad, whole library) | ~15-25% |
| S2 (from S1 survivors) | ~30-40% |
| S3 (from S2 survivors) | ~15-35% |

## Cascade

| Stage | Input | Output (fraction of library) | Job | Model budget |
| --- | --- | --- | --- | --- |
| S1 | Full library | ~2-5% | Cheap, high-recall cut | Fingerprints + descriptors; GBDT or small MLP |
| S2 | S1 survivors | ~0.2-0.5% | Sharpen ranking | All views incl. embeddings; larger MLP or heterogeneous ensemble |
| S3 | S2 survivors | ~0.1% (final) | Final cut on the elite set | Heaviest affordable model; optional cheap physics-style rescoring |

Sizes are placeholders; the recall budget sets them.

**Recall budget:** stage recalls multiply (R = r1 x r2 x r3). S1 is cheapest and widest, so it is the most conservative; S3 the most aggressive. Illustration for R near 60%: r1 ~95%, r2 ~85%, r3 ~75%. Each stage's output size is the smallest set at which it hits its allocated recall on validation.

**Labels sharpen down the cascade** (tighter labels become trainable as acquisition enriches positives):

| Stage | Label |
| --- | --- |
| S1 | Top 1% (or regression target) |
| S2 | ~Top 0.3% |
| S3 | ~Top 0.05% |

The pilot compares binary, regression, and hybrid-loss targets; regression uses the information in the 99% otherwise labeled "inactive."

## Splits and Modeling

| Set | Source | Purpose |
| --- | --- | --- |
| Train | Random + acquired | Fit models |
| Calibration | Pure random only | Conformal p-values |
| Validation | Random, scaffold-aware vs. train | Model selection, view choice, size sweeps |
| Test | Pure random, touched once | End-to-end and per-stage recall |

- Balancing (class weights, mild undersampling) applies to training data only. Calibration, validation, and test stay at natural prevalence, or recall and precision are meaningless for the real library.
- **Models:** GBDT on concatenated features (control), MLP on frozen features (challenger), heterogeneous ensemble of both, over several train/calibration partitions with median aggregation.
- **Feature-view selection:** per-target ablation on that target's own validation data, recorded in its manifest.
- **Conformal step:** model-agnostic wrapper, Mondrian (class-conditional) because the active class is rare.

## Conformal Calibration in the Cascade

- **S1:** calibration is a random library draw, so the guarantee is clean. Rank by confidence difference (P1 minus P0).
- **S2/S3:** calibration must be a random draw from the previous stage's survivors, and a random holdout pushed through S1 leaves too few positives for class-conditional calibration.
- **Recommendation:** formal conformal at S1 only; plain ranking with empirical recall at S2/S3. The goal is a recall target, not an error-rate guarantee, and this saves random dockings for evaluation.
- The guarantee covers error rates at a chosen significance, not recall at a fixed cutoff. Never call the final selection "guaranteed."

## Evaluation and Learning Curve

1. **End-to-end recall comes only from the pure-random holdout** run through the full cascade. This is the gated number.
1. **Per-stage recall** is also measured on the random holdout, conditioned on earlier survivors, to verify the recall allocation.
1. Acquisition-conditioned data is never used to report recall.
1. Model selection uses elite recall at the fixed selection size, not AUC or F1 (a moderate AUC and low F1 can coexist with reasonable early recall, and neither measures recall at a tiny selection fraction).
1. **Learning curve per target** (recall at the final selection fraction vs. training size, **25k up to the full docking budget**). Stop growing where it flattens; store it as a per-target artifact. Minimum viable size differs by target, so it is measured, not assumed.

## Acceptance Gates (predeclared)

- End-to-end elite recall on the untouched test set is at or above the preset threshold.
- Empirical error rates track the chosen significance (S1 calibration check).
- Known actives/decoys for the pocket, where they exist, are recovered at a reasonable rate.
- A small random sample of the final selection, once docked, is clearly shifted toward favorable scores versus a random library sample.

On failure: add training data, an acquisition round, or a stage. Never loosen the gate.

**Post-selection audit:** dock a small random sample of the rejected remainder. It is the only direct estimate of what is being lost and catches silent exclusion of a whole chemotype.

## Known Risks

- **Inherited oracle bias:** the surrogate learns the scoring function's flaws (size and hydrophobicity bias, false-positive accumulation among top scorers). Spend saved compute on rescoring top hits.
- **Diversity loss:** confidence ranking concentrates near training actives. Consider scaffold-aware selection for the final set.
- **Inter-stage shift:** S2 and S3 train on S1-conditioned data. Evaluate each on the population it will actually receive.
- **Training-data bias:** sample from the library being screened; never train on known actives or a narrow set.
- **Evidence base:** several supporting results are recent single-group or retrospective. Treat numbers as guides, not guarantees.

## Open Decisions

1. **Recall target and elite-set definition** (sets stage sizes, docking split, and the gate; fix first).
1. **Number of stages.** Two may suffice; a cascade where every stage is the same model with a sharper threshold is barely a cascade.
1. **Training-sample independence:** independent draws per target (default, uncorrelated errors) vs. a shared sample (cheaper only if per-compound docking prep is cacheable).
1. **Late-stage physics signal:** whether S3 may use a cheap 3D or docking-derived rescoring, which changes what the surrogate is.
1. **Docking engine:** score noise and distribution shape affect thresholding and model choice.
1. **Per-target extra features:** allow pocket-conditioned features alongside the shared store, or keep the store the only feature source.

## Pilot (2-3 targets of different character, e.g. kinase, GPCR, shallow pocket)

- Do embeddings add recall over fingerprints plus descriptors?
- Does the MLP beat GBDT, and does the ensemble beat both?
- How does minimum viable training size vary by target?
- Does S1 reach its allocated recall at the planned output fraction?
- Do S2's extra features buy recall over S1's, measured on S1 survivors?
- How much does the S1-to-S2 shift hurt calibration?

The pilot fixes default views, model family, and stage count; per-target selection stays on regardless.
