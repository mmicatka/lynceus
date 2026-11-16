# Surrogate

## Overview

Active learning using gradient boosted trees over physiochemical feature vectors per target.

Preprocessing of candidates is independent of the target and so the computational cost is amoritized.

## Workflow

```mermaid
flowchart TD

    subgraph FeatureGen ["Feature Generation"]
        Candidates["Candidates"]

        Candidates --> Conformers[("Conformers")]
        Conformers -- "fingerprinting" --> Fingerprints[("Molecular <br>Fingerprints")]

        Conformers --> Features[("Features")]
        Fingerprints --> Features
    end

    subgraph SeedData ["Seed Data (Round 0)"]
        Features --> Samples["Samples<br>(uniform)"]
        Samples --> Docking{"Run<br/>docking"}
        Docking --> Labels[("Labels<br>(Affinity)")]
    end

    subgraph ActiveTraining ["Active Training (Round N)"]
        Features --> TrainSurrogate{"Train <br/> surrogate"}
        Labels --> TrainSurrogate
        TrainSurrogate --> Surrogate[("Surrogate")]

        Surrogate --> PredictLabel{"Predict"}
        Features --> PredictLabel
        PredictLabel --> Scores["Predicted<br/>Affinity"]

        Scores -- "top-k" --> ActiveSet["Active Set"]
        Features -- "random sample" --> UniformSet["Uniform Set"]

        ActiveSet --> RoundSamples["Round Samples"]
        UniformSet --> RoundSamples

        RoundSamples --> Docking{"Run<br/>docking"}
    end
```
