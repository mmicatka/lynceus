# High-level Architecture

## Overview

Lynceus is orchestrated using [Argo Workflows](https://argoproj.github.io/workflows/) running on kubernetes.

## High-level Workflow

```mermaid

flowchart TD

  subgraph CandidatesGraph["Candidates"]
    Candidates[("Candidates")]
  end

  subgraph Target
    ProteinEnsemble["Protein Ensemble"]

    ProteinEnsemble --> Target1["Target 1"]
    ProteinEnsemble --> Target2["Target 2"]
    ProteinEnsemble --> TargetN["Target n"]

    BindingSites["Binding Sites"]

    Target1 --> BindingSites
    Target2 --> BindingSites
    TargetN --> BindingSites
  end

  subgraph SurrogateModel1 ["Surrogate Model 1"]
    BindingSites --> BindingSite1["Binding Site 1"]
    BindingSite1 --> TrainSurrogate1["Train Surrogate 1"]
    Candidates --> TrainSurrogate1
    TrainSurrogate1 --> Surrogate1["Surrogate 1"]
  end

  subgraph SurrogateModel2 ["Surrogate Model 2"]
    BindingSites --> BindingSite2["..."]
    BindingSite2 --> TrainSurrogate2["Train Surrogate 2"]
    Candidates --> TrainSurrogate2
    TrainSurrogate2 --> Surrogate2["Surrogate 2"]
  end

  subgraph SurrogateModelN ["Surrogate Model N"]
    BindingSites --> BindingSiteN["Binding Site 1"]
    BindingSiteN --> TrainSurrogateN["Train Surrogate"]
    Candidates --> TrainSurrogateN
    TrainSurrogateN --> SurrogateN["Surrogate N"]
  end

```

## Components

[surrogate](components/surrogate.md)
