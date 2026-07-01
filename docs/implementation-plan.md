
# Lynceus Implementation Plan

This section translates the conceptual pipeline into a concrete build plan targeting **Dagster** as the orchestration layer, **Python** managed with **uv**, and open-source cheminformatics/simulation tooling (**RDKit**, **OpenMM**, **AutoDock-GPU / AutoDock Vina**). It is intentionally implementation-*planning*-level: it defines the asset graph, data contracts, resources, and deliverables needed before writing code, not the code itself.

## Guiding Engineering Principles

- **Assets, not ad-hoc scripts.** Every named artifact in the conceptual diagram (Targets, Target Surfaces, Candidates, Filtered Candidates, Training Complexes, Surrogate Model, Complexes, etc.) becomes a Dagster software-defined asset with an explicit, versioned schema. This gives lineage, caching, and partial re-materialization for free — important given how expensive some stages are.
- **Partitioning as a first-class concern.** Target ensembles partition naturally by conformational state; candidate libraries partition naturally by chunk/batch. Both should be modeled as Dagster partitions (static partitions for target states, dynamic partitions for candidate batches) so that expensive steps (conformer generation, complex generation) can be scaled out, retried, and re-run selectively without reprocessing everything.
- **Pluggable backends behind stable interfaces.** Per your direction, ensemble generation should support multiple backends (MD-based via OpenMM, multi-model structure prediction, or both) behind a common interface/contract, selected via Dagster resource configuration rather than hardcoded per-pipeline. Likewise, docking/scoring should support both AutoDock-GPU and AutoDock Vina behind a common "docking engine" resource interface, so the engine is a config choice, not a code fork.
- **Separation of cheap vs. expensive compute.** Dagster resources should distinguish lightweight steps (filtering, featurization, inference) that can run on standard compute from expensive steps (MD, docking) that need GPU/HPC-backed execution — likely via separate Dagster executors, run launchers, or external step launchers (e.g., a compute-cluster-backed launcher for docking/MD steps).
- **Reproducibility of the training subsample.** Because Stage 3's surrogate model is only as good as the representativeness of its training subsample, the sampling strategy, random seeds, and diversity metrics used must be captured as asset metadata, not just implicit in code — this is what makes it possible to audit or regenerate a surrogate model later.

## Repository & Environment Structure

- **Package manager:** `uv` for all environment/dependency management; a single `pyproject.toml` at the repo root defining the project and its dependency groups (core, MD, docking, dagster, dev/test).
- **Suggested top-level package layout** (planning-level, not final):
  - `lynceus/target/` — target retrieval, ensemble generation backends, surface derivation
  - `lynceus/recognizer/` — candidate retrieval, physiochemical filters
  - `lynceus/surrogate/` — training sampling, featurization, model training/inference
  - `lynceus/screening/` — model-based filtering, conformer generation, complex generation (shared with training-time complex generation via common modules)
  - `lynceus/common/` — shared schemas (e.g., molecule/target representations), shared I/O utilities, shared Dagster resource base classes
  - `lynceus/pipeline/` — Dagster definitions: assets, resources, jobs, schedules/sensors, partitions
- **Dependency groups to define in `pyproject.toml`:** RDKit (cheminformatics, filtering, conformer generation), OpenMM (MD-based ensemble generation), AutoDock-GPU and AutoDock Vina (docking/complex generation — note these are external binaries/CLI tools rather than pip packages, so the plan should account for wrapping them as Dagster resources that shell out or bind via existing Python wrappers), Dagster + dagster-webserver for orchestration, plus a modeling library group (left open/pluggable) for the surrogate model itself.
- **External binary management:** AutoDock-GPU and AutoDock Vina are compiled binaries, not Python packages — the plan should include a strategy for how these are provisioned in the execution environment (e.g., containerized Dagster op/asset execution with the binaries pre-installed in the image) so environment setup isn't left implicit.

## Data Contracts (Cross-Cutting Deliverable)

Before building individual assets, define shared, versioned schemas for the objects that cross stage boundaries, since these are the actual interfaces between teams/modules:

| Object | Produced by | Consumed by | Key fields to define |
| --- | --- | --- | --- |
| Target | Target stage | Ensemble generation | identifier, source structure reference, provenance |
| Target Ensemble / Surfaces | Target stage | Complex generation (both stages) | conformer ID, state label, pocket/surface definition, generation method used |
| Candidate | Recognizer stage | Filtering, conformer generation | identifier, source library reference, structure (e.g., SMILES) |
| Filtered Candidate | Recognizer stage | Sampling, model filter | candidate ID, filter pass/fail flags and reasons, physiochemical properties computed |
| Training Complex | Surrogate Model stage | Model training | candidate ID, target state ID, complex/pose representation, score(s) from docking engine |
| Surrogate Model (artifact) | Surrogate Model stage | Model filter | model version, training data reference, training metadata (sampling method, seed, diversity metrics) |
| Candidate Conformer | Screening stage | Complex generation | candidate ID, conformer set, generation method/parameters |
| Complex (final) | Screening stage | Downstream selection | candidate ID, target state ID, pose, docking engine + score, provenance chain back to target ensemble + candidate library version |

This table itself is a deliverable — it should be fleshed out and agreed on before asset code is written, since changing these schemas later is expensive.

### Stage 1 — Target: Implementation Plan

**Assets to define:**

- `raw_targets` — retrieval asset; pulls starting structures for target protein(s). Resource-backed (structure source is a config/resource, not hardcoded) so different sources can be swapped in.
- `target_ensemble` — partitioned asset (partition = target, and potentially sub-partitioned by generation run) that produces conformers via a pluggable ensemble-generation resource. Two backend implementations to plan for as interchangeable resources:
  - **MD-based backend (OpenMM):** enhanced-sampling or standard MD trajectories, followed by conformer extraction/clustering to select a representative, non-redundant subset of states.
  - **Structure-prediction-based backend:** multiple independently generated structural models used as an ensemble proxy.
  - Both backends should conform to the same output contract (a set of labeled conformers) so the rest of the pipeline is agnostic to which was used, and so a future backend can be added without touching downstream stages.
- `target_surfaces` — derives pocket/surface definitions per conformer in the ensemble. Plan for this to be its own asset (not fused into ensemble generation) since surface/pocket definition may itself involve a choice of method and may need independent re-computation if pocket-definition logic changes without regenerating the whole ensemble.

**Deliverables for this stage:**

- Interface definition for the "ensemble generation backend" resource (inputs/outputs, not implementation).
- Interface definition for the "surface/pocket definition" step, independent of which ensemble backend produced the conformers.
- Partitioning scheme for target states (static partition set per target, since the number of relevant states is typically known/bounded per project).
- Clustering/redundancy-reduction strategy for MD-derived conformers (how many representative states to retain, by what criterion) — to be specified before implementation since it directly controls downstream cost.

### Stage 2 — Recognizer: Implementation Plan

**Assets to define:**

- `raw_candidates` — retrieval asset for the candidate library; resource-backed for library source.
- `filtered_candidates` — applies physiochemical filters (PAINS, CNS-MPO, or others as configured) using RDKit as the primary filtering/featurization engine. Should output not just a pass/fail library but the filter results as metadata (which filters fired, computed properties) so filtering decisions are auditable.

**Deliverables for this stage:**

- Enumerated, versioned list of which physiochemical filters are in scope for v1 (e.g., PAINS substructure filters, CNS-MPO, standard drug-likeness/property filters) and their pass/fail thresholds — a configuration deliverable, not just a code interface.
- Decision on candidate library partitioning strategy (batch size for dynamic partitions) based on expected library scale, since this determines how Stages 3–4 parallelize.
- Since this library is likely very large, plan for a scalable execution path (e.g., chunked/batched asset materialization rather than a single monolithic in-memory step) from the start.

### Stage 3 — Surrogate Model: Implementation Plan

**Assets to define:**

- `training_candidates` — sampling asset that draws the representative training subsample from `filtered_candidates`. Sampling strategy (e.g., diversity-based, property-stratified, random with fixed seed) should be a configurable resource so it can be changed/audited without touching pipeline structure.
- `training_conformers` — conformer generation for the training subsample only (RDKit-based conformer generation as the default/pluggable engine).
- `training_complexes` — docking/complex generation for training conformers against `target_surfaces`, using the pluggable docking engine resource (AutoDock-GPU or AutoDock Vina, selected via config).
- `surrogate_model` — trained model artifact. Modeling approach itself is left open per your direction, but the asset should capture: training data reference (exact `training_complexes` version), featurization method, model type/version, and evaluation metrics (e.g., held-out performance against a validation split of training complexes).

**Deliverables for this stage:**

- Interface definition for the "docking engine" resource so AutoDock-GPU and AutoDock Vina are truly interchangeable (common input: candidate conformer + target surface; common output: pose + score, normalized across engines since Vina and AutoDock-GPU scoring conventions differ).
- Sampling strategy specification (method, target sample size as a function of full library size, diversity criteria) — needed before this asset can be built since it's a methodological choice with real downstream consequences.
- Model validation plan: what held-out evaluation looks like, what performance threshold is required before the model is trusted to filter the full library in Stage 4.
- Retraining/versioning policy: when the surrogate model needs to be regenerated (e.g., if target ensemble changes, if training sample composition changes) — this should be encoded as asset dependencies so Dagster's built-in staleness tracking can flag when `surrogate_model` is out of date relative to its upstream assets.

### Stage 4 — Ensemble Screening: Implementation Plan

**Assets to define:**

- `model_filtered_candidates` — applies `surrogate_model` to the *full* `filtered_candidates` set (not the training subsample), producing a much smaller downstream set. This is likely the highest-throughput inference step in the pipeline and should be planned for batched/parallelized execution.
- `candidate_conformers` — same conformer generation logic as Stage 3's `training_conformers` (ideally the same underlying asset/op, parameterized by which candidate set it's given, to avoid duplicated logic), applied to the surrogate-filtered set.
- `complexes` — final docking/complex generation using the same docking engine resource interface as Stage 3, against `target_surfaces`, for the surrogate-filtered candidate set.

**Deliverables for this stage:**

- Reuse plan confirming `training_conformers`/`candidate_conformers` and the two `Complex Generation` steps share the same underlying Dagster ops/resources, parameterized by input partition — this avoids maintaining two implementations of the same logic, consistent with the note in Design Notes that both complex-generation steps serve different purposes but share the same mechanism.
- Threshold/cutoff specification for the Model Filter step (e.g., top-N, score threshold) — a configuration deliverable.
- Output contract for final `complexes`, including full provenance chain (target ensemble version, candidate library version, surrogate model version, docking engine + parameters) so results are traceable end-to-end.

### Cross-Stage Deliverables

- **Dagster resource catalog:** a single document enumerating every pluggable resource (ensemble generation backend, surface definition method, physiochemical filter set, sampling strategy, docking engine, model type) with its interface contract — this is the artifact that lets the "pluggable" design goal actually hold up as the codebase grows.
- **Partitioning & scaling plan:** target-state partitions (static) and candidate-batch partitions (dynamic), plus a plan for which steps run on standard compute vs. GPU/HPC-backed execution, and how Dagster run launchers/executors are configured for each.
- **Provenance/lineage requirements:** since the platform's value depends on being able to trace a final candidate back to the specific target conformational state it was screened against, every asset's metadata should carry enough information (IDs + versions of upstream assets) to reconstruct that chain — this should be specified as a cross-cutting requirement rather than left to each stage individually.
- **Environment/CI plan:** `uv`-managed dependency groups, containerized execution for steps requiring external binaries (AutoDock-GPU, AutoDock Vina, OpenMM's compiled dependencies), and a test strategy distinguishing fast unit tests (schema/interface validation, filter logic) from slow integration tests (actual MD runs, actual docking runs) that likely only run on a subset of CI triggers given their cost.

### Suggested Build Order

1. **Data contracts + resource catalog** (schemas and interfaces only, no implementation) — everything else depends on these being stable.
1. **Stage 2 (Recognizer)** — simplest stage, no external simulation/docking dependencies, good for validating the Dagster asset/partition scaffolding early.
1. **Stage 1 (Target)**, starting with one ensemble-generation backend (whichever is more readily available — structure-prediction-based ensembles are typically faster to stand up than MD, so may be a reasonable first backend even though both are planned).
1. **Stage 3 (Surrogate Model)**, starting with a single docking engine (e.g., AutoDock Vina, as the more lightweight/CPU-friendly option) before adding AutoDock-GPU as a second backend to validate the docking-engine interface is truly interchangeable.
1. **Stage 4 (Ensemble Screening)**, largely reusing Stage 3's conformer/complex-generation logic — this stage should be fast to build once Stage 3 is solid, since the main new asset is the model filter step.
1. **Second backend/engine additions** (MD-based ensemble generation, AutoDock-GPU) once the pluggable interfaces have been proven out with one implementation each — deliberately deferred so the interface design is validated before doubling implementations.
