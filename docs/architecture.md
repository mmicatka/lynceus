# Lynceus Architecture

**Scope:** Structured protein targets + ZINC22 small molecule ligands
**Orchestration:** Dagster (asset-centric, Kubernetes execution backend)

## Pipeline Overview

Five independently deliverable modules. Modules 1 and 2 run in parallel and
converge at Module 3.

```text
Module 1: Compound Library Preparation
Module 2: Target Representation
         \
          --> Module 3: Recognition Module Discovery (ML filter + docking)
                    \
                     --> Module 4: Outcome-Specific Scoring
                               \
                                --> Module 5: Candidate Ranking + Output
```

| Module | Document |
| --- | --- |
| 1: Compound Library Preparation | `module_1_compound_library.md` |
| 2: Target Representation | `module_2_target_representation.md` |
| 3: Recognition Module Discovery | `module_3_recognition.md` |
| 4: Outcome-Specific Scoring | `module_4_scoring.md` |
| 5: Candidate Ranking and Output | `module_5_ranking.md` |

## Conventions

- All compute scripts are pure CLI tools (`argparse`, `if __name__ == "__main__"`)
- Dagster assets call scripts via `PipesSubprocessClient` locally or
  `PipesK8sClient` in production; no Dagster imports inside scripts
- Persistent state lives in Parquet (Polars) or JSON; no pickled Python objects
  at module boundaries
- GPU assets declare `dagster/priority` tags and request `nvidia.com/gpu: 1`
  in the Kubernetes pod spec
- All file paths are injected via CLI args; scripts are location-agnostic
- Partitioning strategy: fixed-size compound partitions established at
  download time, referenced via a `partitions.json` manifest throughout

## Module Interfaces

These are the boundary artifacts between modules. Each is a well-defined file
format; modules on either side of a boundary can be developed and tested
independently.

| Artifact | Producer | Consumer | Format |
| --- | --- | --- | --- |
| `library/partitions.json` | Module 1 | Module 3 | JSON |
| `library/partitioned/*.parquet` | Module 1 | Module 3 | Parquet |
| `targets/{target_id}/ensemble.json` | Module 2 | Module 3 | JSON |
| `screening/{target_id}/docking/scores.parquet` | Module 3 | Module 4 | Parquet |
| `screening/{target_id}/docking/poses/*.sdf` | Module 3 | Module 4 | SDF |
| `screening/{target_id}/rescoring/rescored.parquet` | Module 4 | Module 5 | Parquet |

## Project Structure

```bash
lynceus/
  dagster.yaml
  pyproject.toml
  lynceus/
    __init__.py
    assets/
      compound_library.py      # Module 1 assets
      target_representation.py # Module 2 assets
      ml_filter.py             # Module 3a assets
      docking.py               # Module 3b assets
      rescoring.py             # Module 4 assets
      ranking.py               # Module 5 assets
    resources/
      docking_engine.py        # AutoDock-GPU / Vina resource abstraction
      k8s.py                   # PipesK8sClient config
    config/
      schema.py                # Pydantic config models
    scripts/
      compound_library/
        download_tranches.py
        filter_library.py
        repartition.py
      target/
        fetch_pdb.py
        fix_receptor.py
        generate_conformers.py
        prepare_pdbqt.py
        detect_pockets.py
        generate_grids.py
        build_ensemble.py
      ml_filter/
        sample_seeds.py
        generate_conformers.py
        dock_seeds.py
        train_surrogate.py
        score_library.py
        select_top.py
      docking/
        generate_conformers.py
        run_docking.py
        aggregate_scores.py
      rescoring/
        select_candidates.py
        run_gnina.py
        parse_gnina.py
      ranking/
        triage_hits.py
        rank_hits.py
    utils/
      receptor.py              # ReceptorEnsemble dataclasses (stdlib only)
      parquet.py               # Shared Polars schema constants
      fingerprints.py          # Morgan FP packing/unpacking
  config/
    config.yaml
  k8s/
    values.yaml                # Dagster Helm values
    pod_templates/
      gpu_pod.yaml
      cpu_pod.yaml
```

## Configuration Schema

```yaml
target:
  pdb_id: "6XR9"
  target_id: "hsp90_human"
  fix:
    ph: 7.4
  conformers:
    strategy: single          # single | multi_pdb | md
    additional_pdb_ids: []
  pocket:
    min_sasa: 0.25
    primary_pocket_id: null   # auto-select highest-scoring if null

zinc22:
  mw_range: [200, 500]
  logp_range: [-1, 5]
  subset: "for-sale"

filters:
  cns_mpo_min: 4.0
  pains: true

docking_engine: autodock_gpu  # autodock_gpu | vina
tools:
  autodock_gpu: /usr/local/bin/AutoDock-GPU
  autogrid4: /usr/local/bin/autogrid4
  gnina: /usr/local/bin/gnina

ml_filter:
  seed:
    size: 50000
    strategy: maxmin          # random | maxmin
  model:
    type: lightgbm
    min_spearman_r: 0.55      # validation gate
  selection:
    top_fraction: 0.01

docking:
  exhaustiveness: 8
  num_modes: 9
  temperature_k: 298.15

rescoring:
  top_fraction: 0.01          # fraction of docking hits to rescore
```

## Implementation Order

Each phase produces a usable intermediate result and can be validated
independently before proceeding.

1. **Foundation**

- Module 2 (Target Representation) in full
- Module 1 through `partitions_manifest`
- Validate: `ensemble.json` is well-formed; pocket detection is reproducible;
  compound counts match expectations

**Phase 2** - ML Pre-filter

- Module 3a (ML Pre-filter) through `surrogate_model`
- Validate: surrogate model clears the `min_spearman_r` gate on held-out seed
  docking results

**Phase 3** -- Full Screening

- Module 3a `library_ml_scores` + `ml_filter_selected`
- Module 3b (Ensemble Docking) in full
- Validate: docking score distributions are sensible; no missing ZINC IDs

**Phase 4** -- Scoring and Output

- Module 4 (Rescoring) in full
- Module 5 (Ranking) in full
- Validate: `summary.json` compound counts are consistent end-to-end;
  top hits have known HSP90 ligand scaffolds (PoC sanity check)

**Phase 5** -- Production Hardening

- Kubernetes execution backend wired up for all GPU assets
- Dagster sensor for automatic re-screening on updated compound library
- Per-asset metadata logging (compound counts, score distributions, timing)
- Multi-target support (additional `target_id` values through same asset graph)
