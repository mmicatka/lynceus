# Lynceus

Named after the mythological figure renowned for extraordinary vision,
reflecting the platform's goal of identifying transient conformations,
cryptic interfaces, and actionable protein states that are not apparent
from static structures.

**Lynceus** is a generic, modular computational platform for discovering
molecules that recognize specific protein conformational states and
couple that recognition to a desired biological outcome.

The platform is intentionally **mechanism-agnostic**. Rather than being
limited to targeted degradation (e.g., PROTACs), it is designed to
support any functional strategy that begins with selective recognition
of a protein state.

## Core Principles

- **Ensemble-first:** represent proteins as dynamic conformational
    ensembles instead of single static structures.
- **Surface-centric:** identify accessible surfaces and epitopes
    rather than assuming classical binding pockets.
- **Modular:** separate target recognition from downstream biological
    function.
- **Outcome-agnostic:** enable degradation, aggregation inhibition,
    imaging, stabilization, or future modalities without architectural
    changes.
- **Extensible:** each module can evolve independently as new
    algorithms or experimental data become available.

## High-Level Architecture

```text

Target Representation
        ↓
Conformational Ensemble Generation
        ↓
Surface / Epitope Identification
        ↓
Recognition Module Discovery
        ↓
Functional Module Selection
        ↓
Candidate Complex Generation
        ↓
Dynamic Refinement
        ↓
Outcome-Specific Scoring
        ↓
Candidate Ranking
```

## Pipeline Modules

### 1. Target Representation

Input may include:

- Experimental structures (PDB)
- MD-generated ensembles
- Cryo-EM structures
- Predicted structures
- Oligomers or aggregate models

The pipeline operates on ensembles regardless of source.

### 2. Conformational Ensemble Generation

Generate representative conformational states using:

- Molecular dynamics
- Enhanced sampling
- Structural clustering

Representative clusters become candidate target states.

### 3. Surface / Epitope Identification

Characterize candidate recognition regions using properties such as:

- Solvent accessibility
- Electrostatics
- Hydrophobicity
- Flexibility
- Secondary structure persistence
- Surface topology

This supports both structured proteins and intrinsically disordered or aggregated systems.

### 4. Recognition Module Discovery

Potential recognition elements include:

- Small molecules
- Peptides
- Mini-proteins
- Nanobodies
- Macrocycles
- Future binding scaffolds

### 5. Functional Module Selection

Recognition is decoupled from biological function.

Examples include:

| Desired Outcome | Functional Module |
| --- | --- |
| Targeted degradation | E3 ligase recruiter |
| Autophagic clearance | LC3/autophagy adaptor |
| Secondary nucleation inhibition | Surface-blocking ligand |
| Fibril end capping | End-binding ligand |
| Aggregate stabilization | State-selective binder |
| Imaging | Reporter/probe |

### 6. Candidate Complex Generation

Enumerate plausible assemblies by combining:

- Target conformations
- Recognition modules
- Functional modules
- Linker or interface geometries (when applicable)

No single "correct" ternary complex is assumed; instead, the platform
samples a population of plausible functional complexes.

### 7. Dynamic Refinement

Evaluate candidates using molecular dynamics to assess:

- Binding persistence
- Interface stability
- Conformational adaptation
- Linker flexibility (if relevant)
- Overall complex robustness

### 8. Outcome-Specific Scoring

Scoring depends on the desired biological outcome.

Generic metrics:

- Recognition affinity
- Ensemble robustness
- Interface stability
- Selectivity
- Conformational persistence

Examples of outcome-specific metrics:

- Degradation:
  - productive
  - recruitment geometry
- Secondary nucleation inhibition:
  - fibril surface occupancy and blocking persistence
- Imaging:
  - probe accessibility and specificity

### 9. Candidate Ranking

Rank candidates across the entire ensemble rather than a single
structure.

Outputs may include:

- Recognition modules
- Functional modules
- Stable complex ensembles
- Confidence metrics
- Mechanism-specific rankings

## Current Direction

The initial implementation will:

1. Start from experimental PDB structures.
1. Expand to MD-generated conformational ensembles.
1. Cluster ensembles into representative states.
1. Identify dynamic recognition surfaces.
1. Support multiple functional outcomes without modifying the core architecture.
