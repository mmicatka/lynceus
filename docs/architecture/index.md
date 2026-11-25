# High-Level Architecture

## Overview

Lynceus is orchestrated with [Argo Workflows](https://argoproj.github.io/workflows/) running on Kubernetes.

A single run carries one target ensemble. Binding sites are detected on every ensemble member and consolidated into a distinct set of physical binding sites. From that point on, each binding site gets its own independent surrogate model, trained against the shared candidate library.

This page shows how the stages fit together. Candidate preparation and surrogate modeling are covered in detail on their own pages.

## High-Level Workflow

```mermaid
flowchart TD
  Candidates[("Candidates")]

  subgraph Target["Target"]
    ProteinEnsemble["Protein Ensemble"]

    ProteinEnsemble --> Member1["Ensemble Member 1"]
    ProteinEnsemble --> Member2["Ensemble Member 2"]
    ProteinEnsemble --> MemberN["Ensemble Member N"]

    Member1 --> BindingSites["Binding Sites"]
    Member2 --> BindingSites
    MemberN --> BindingSites
  end

  subgraph SurrogateModel1["Surrogate Model 1"]
    BindingSites --> BindingSite1["Binding Site 1"]
    BindingSite1 --> TrainSurrogate1["Train Surrogate"]
    Candidates --> TrainSurrogate1
    TrainSurrogate1 --> Surrogate1["Surrogate 1"]
  end

  subgraph SurrogateModel2["Surrogate Model 2"]
    BindingSites --> BindingSite2["Binding Site 2"]
    BindingSite2 --> TrainSurrogate2["Train Surrogate"]
    Candidates --> TrainSurrogate2
    TrainSurrogate2 --> Surrogate2["Surrogate 2"]
  end

  subgraph SurrogateModelN["Surrogate Model N"]
    BindingSites --> BindingSiteN["Binding Site N"]
    BindingSiteN --> TrainSurrogateN["Train Surrogate"]
    Candidates --> TrainSurrogateN
    TrainSurrogateN --> SurrogateN["Surrogate N"]
  end
```

## Further Reading

- [Candidates](candidates.md): how candidate libraries are retrieved, preprocessed, repartitioned, and filtered before screening.
- [Surrogate Model](surrogate.md): how each per-site surrogate is trained, and how it is used to filter the full library before docking.
