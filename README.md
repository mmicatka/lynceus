# Lynceus

![Project Status: Work in Progress](https://img.shields.io/badge/status-WIP-yellow)

> [!WARNING]
> **Active Development / Work in Progress**
> This project is currently in early-stage development (**Alpha**). Features and APIs are unstable and subject to breaking changes without notice. **Not suitable for production use yet.**
> Major refactor in progress

## Overview

Named after the mythological figure renowned for extraordinary vision, reflecting the platform's goal of identifying transient conformations, cryptic interfaces, and corresponding actionable protein states.

**Lynceus** is a modular computational platform for discovering molecules that recognize specific protein conformational states and couple that recognition to a desired biological outcome.

## Motivation

Most ligand discovery pipelines treat a target protein as a single rigid structure - typically whatever conformation happens to be available from a crystal structure or a single predicted model. This is a poor approximation of reality. Proteins are dynamic ensembles: they sample multiple conformational substates, some only transiently, and a substantial fraction of biologically important recognition events (allosteric regulation, cryptic pocket opening, order-disorder transitions, conformational selection in signaling) depend on states that are rare, short-lived, or simply absent from static structural databases.

Lynceus is built around the premise that **conformational state is itself the design target**, not an afterthought to be handled by post-hoc induced-fit correction. The platform generates a representative ensemble of target states up front, screens against that ensemble (rather than a single structure), and uses a trained surrogate model to make ensemble-aware screening tractable at library scale. The outputs are candidates (small molecules, proteins, etc.) with an associated *state preference*, the information needed to couple binding to a specific functional or biological outcome (e.g., stabilizing an inactive state, blocking an interface that only forms transiently, or selectively engaging a disease-associated conformation over the wild-type/resting one).

## Architecture

A single run carries one target ensemble. Ensemble members fan out for binding-site detection, which runs once per member (internal parallelism is handled in Python, since it isn't computationally expensive enough to warrant per-member tasks). Per-member sites are then deduplicated into a distinct set of physical binding sites, each carrying a site identifier and the member(s) it was found in. From that point forward, every stage - surrogate training, the eventual full-library filter pass, and docking - runs once per deduplicated binding site as an independent fan-out, not once per run.

```mermaid

flowchart TD

  subgraph Target
    RetrieveTargets[/"Retrieve Target(s)"/] --> Targets@{ shape: st-rect, label: "Targets" }
    Targets --> EnsembleGeneration{{"Target Ensemble Generation"}}
    EnsembleGeneration --> EnsembleMembers@{shape: st-rect, label: "Ensemble Members"}
    EnsembleMembers -- "fan out per member" --> DetectBindingSites{{"Detect Binding Sites"}}
    DetectBindingSites --> MemberBindingSites@{shape: st-rect, label: "Per-Member Binding Sites"}
    MemberBindingSites --> DedupBindingSites{{"Dedup Binding Sites"}}
    DedupBindingSites --> BindingSites@{shape: st-rect, label: "Binding Sites"}
  end

  subgraph Candidate
    RetrieveCandidates@{ shape: st-rect, label: "Retrieve Candidates"} --> Candidates@{ shape: st-rect, label: "Candidates" }
    Candidates --> Preprocessing["Preprocessing"]
    Preprocessing --> Repartition["Repartition"]
    Repartition --> BalancedCandidates@{ shape: st-rect, label: "Candidates" }
    BalancedCandidates --> PhysioChemFilter{"Physiochemical Filter(s)<br>(PAINS, CNS-MPO, etc.)"}
    PhysioChemFilter --> FilteredCandidates@{shape: st-rect, label: "Filtered Candidates"}
  end

  subgraph Surrogate Model [Surrogate Model - per Binding Site]
    FilteredCandidates -- "sample" --> TrainingCandidates@{ shape: st-rect, label: "Training Candidates" }

    TrainingCandidates --> ModelComplexGeneration["Complex Generation"]
    BindingSites -- "fan out per site" --> ModelComplexGeneration

    ModelComplexGeneration --> TrainingComplexes@{shape: st-rect, label: "Training Complexes"}

    TrainingComplexes --> TrainModel["Train Model"]
    TrainModel --> SurrogateModel@{shape: cyl, label: "Surrogate Model"}
  end

  subgraph Surrogate Model Filter [Surrogate Model Filter - per Binding Site]
    SurrogateModel --> SurrogateModelFilter{"Model Filter"}
    FilteredCandidates -- "full library" --> SurrogateModelFilter
    SurrogateModelFilter --> SurrogateFilteredCandidates@{shape: st-rect, label: "Surrogate Filtered Candidates"}
  end

  subgraph Complex Generation [Complex Generation - per Binding Site]
    SurrogateFilteredCandidates --> SurrogateFilteredCandidateConformerGeneration{{"Conformer Generation"}}
    SurrogateFilteredCandidateConformerGeneration --> CandidateConformers@{ shape: st-rect, label: "Candidate Conformers"}

    CandidateConformers --> ComplexGeneration["Complex Generation"]
    BindingSites --> ComplexGeneration

    ComplexGeneration --> Complexes@{shape: st-rect, label: "Complexes"}
  end

```

## Development Environment

To test these workflows, you need an existing Kubernetes cluster (like k3s, minikube, or kind) with Argo Workflows installed.

If you don't have Argo set up yet, you can use the included helper script:

```bash
cd scripts/setup-argo
cp .env.example .env
make all
```
