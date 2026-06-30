# Lynceus

Named after the mythological figure renowned for extraordinary vision,
reflecting the platform's goal of identifying transient conformations,
cryptic interfaces, and actionable protein states that are not apparent
from static structures.

**Lynceus** is a modular computational platform for discovering molecules that
recognize specific protein conformational states and couple that recognition to a
desired biological outcome.

This document describes the implementation targeting **small molecule
ligands against structured (folded) proteins**.

---

## Core Principles

- **Ensemble-first:** represent proteins as conformational ensembles rather than
  single static structures.
- **Surface-centric:** identify accessible pockets and epitopes rather than
  assuming a single canonical binding site.
- **Modular:** separate target recognition from downstream biological function.
- **Extensible:** each module evolves independently as new algorithms or
  experimental data become available.

---

## Scope

| Dimension | Approach |
| --- | --- |
| Target class | Structured (folded) proteins; experimental PDB structures |
| Recognition module | Small molecules |
| Functional module | Binding (recognition only) |
| Ensemble generation | Structural clustering of existing PDB conformers |
| Complex generation | Ligand pose enumeration from docking |
| Dynamic refinement | Pass-through (stub) |
| Outcome scoring | Recognition affinity, ensemble robustness |

---

## High-Level Architecture

```mermaid

flowchart TD



```

```text
Target Representation
        |
        v
Conformational Ensemble Generation
        |
        v
Surface / Pocket Identification
        |
        v
Recognition Module Discovery      <-- small molecules
        |
        v
Functional Module Selection       <-- stub; outcome = "binding"
        |
        v
Candidate Complex Generation      <-- ligand pose enumeration
        |
        v
Dynamic Refinement                <-- pass-through stub
        |
        v
Outcome-Specific Scoring          <-- affinity + ensemble robustness
        |
        v
Candidate Ranking
```

---

## Pipeline Modules

### 1. Target Representation

**Inputs:** experimental PDB structures only.

The module emits a `TargetRepresentation` carrying one or more structures and
their associated metadata.

**Output interface:** a `TargetRepresentation` has a name, a list of one or
more PDB structures, and a source label (currently always `"pdb"`).

### 2. Conformational Ensemble Generation

**Behavior:** structural clustering of the input PDB conformers into
representative states. No MD or enhanced sampling is performed.

Each cluster centroid becomes a candidate receptor state. Weights default to
uniform across states.

**Output interface:** each `ConformerEntry` carries a structure, a state ID,
a weight (uniform across states), and a set of annotations (e.g. secondary
structure, RMSD to reference). A `ReceptorEnsemble` bundles the target
representation with its list of conformer entries.

### 3. Surface / Pocket Identification

Characterize candidate recognition regions across the ensemble using:

- Pocket detection (fpocket)
- Solvent accessibility (FreeSASA)
- Docking box definition from pocket centroids
The output is a set of `PocketSite` records associated with each conformer,
carrying geometry (centroid, dimensions) and surface properties.

**Output interface:** a docking box is defined by a center coordinate and
dimensions. Each `PocketSite` references its conformer and pocket ID, carries
a docking box, a druggability score, and a solvent exposure value.

### 4. Recognition Module Discovery

**Behavior:** small molecule virtual screening via an ML-guided docking
funnel.

**Recognition module type:** the recognition module is a small molecule,
identified by SMILES string, a molecule ID, and its source library.

**Screening funnel:**

1. Download compound library tranches (ZINC22 or equivalent)
1. Standardize and filter (CNS-MPO, PAINS)
1. Seed subset selection (random or diversity-based; configurable)
1. Conformer generation for seed subset only
1. Seed docking against primary receptor ensemble
1. Surrogate model training (LightGBM on Morgan fingerprints)
1. Full-library scoring and top-N% selection
1. Conformer generation for selected subset
1. Full ensemble docking of selected subset
1. CNN rescoring of top docking hits (gnina)

### 5. Functional Module Selection

**Behavior:** stub. No functional module is attached; the outcome is
recorded as `"binding"`.

**Output interface:** a `FunctionalModule` has an outcome label (always
`"binding"`) and an optional payload (unused).

### 6. Candidate Complex Generation

**Behavior:** ligand pose enumeration from docking. Each docking pose
for a given (ligand, receptor conformer) pair is a candidate complex.

**Output interface:** a `CandidateComplex` pairs a recognition module with a
functional module, and records the receptor conformer ID, pose ID, pose
coordinates (an SDF block or file reference), and docking score.

### 7. Dynamic Refinement

**Behavior:** pass-through stub. Input complexes are forwarded unchanged.

**Interface (in = out):** a `RefinedComplex` wraps the original candidate,
a refinement method (`"none"` for the stub), refined pose coordinates, and
stability metrics (empty for the stub).

### 8. Outcome-Specific Scoring

**Behavior:** recognition affinity and ensemble robustness.

**Output interface:** a `ScoringResult` references its complex ID and
mechanism (`"binding"`), and carries a scores dictionary (e.g. affinity:
-8.2, ensemble robustness: 0.74) plus metadata.

**Score components:**

- `affinity`: primary docking score (minimum across ensemble for multi-conformer targets)
- `cnn_score`: gnina CNN rescore where available
- `ensemble_robustness`: fraction of ensemble conformers in which the ligand docks productively

### 9. Candidate Ranking

Rank `ScoringResult` records across the full ensemble. Output includes ranked
recognition modules, score breakdowns, and confidence metrics.

Ranking operates on the `scores` dict.

---

## Repository Structure

Follows Snakemake / Dagster best practices with clear separation of
receptor-agnostic and receptor-dependent stages.

```bash
lynceus/
  config/
  workflow/
    Snakefile
    rules/
      ligand_candidate.smk
      receptor.smk
      screening/
    scripts/
      ligand_candidate/
      receptor/
      screening/
    envs/
      ligand_candidate/
      receptor/
      screening/
  results/
    ligand_candidate/
    receptor/
    screening/{receptor_name}/
  logs/
  docs/
  notebooks/
```

---

## Configuration

All pipeline parameters are defined in `config/config.yaml`.

Key parameters:

```yaml
docking_engine: autodock_gpu       # vina | autodock_gpu
 
ligand_candidate:
  seed_subset_size: 50000
  seed_selection_strategy: diversity  # random | diversity
  top_n_fraction: 0.01
 
ml_filter:
  model: lightgbm
  fingerprint_radius: 2
  fingerprint_bits: 2048
 
docking:
  top_rescore_fraction: 0.05
 
tools:
  autodock_gpu: /usr/local/bin/AutoDock-GPU
  gnina: /usr/local/bin/gnina
  fpocket: /usr/local/bin/fpocket
```
