# Surrogate

## Overview

Active learning using gradient boosted trees over molecular fingerprint features, trained per binding site.

Fingerprints are computed from the conformers produced during [candidate preprocessing](candidates.md). Preprocessing is independent of the binding site, so its computational cost is amortized across every surrogate.

## Workflow

```mermaid
flowchart TD

    subgraph FeatureGen ["Feature Generation"]
        Candidates[("Preprocessed<br>Candidates")]
        Candidates -- "fingerprinting" --> Fingerprints[("Molecular<br>Fingerprints")]
    end

    subgraph SeedData ["Seed Data (Round 0)"]
        Fingerprints --> Samples["Samples<br>(uniform)"]
        Samples --> Docking{"Run<br/>docking"}
        Docking --> Labels[("Labels<br>(Affinity)")]
    end

    subgraph ActiveTraining ["Active Training (Round N)"]
        Fingerprints --> TrainSurrogate{"Train<br/>surrogate"}
        Labels --> TrainSurrogate
        TrainSurrogate --> Surrogate[("Surrogate")]

        Surrogate --> PredictLabel{"Predict"}
        Fingerprints --> PredictLabel
        PredictLabel --> Scores["Predicted<br/>Affinity"]

        Scores -- "top-k" --> ActiveSet["Active Set"]
        Fingerprints -- "random sample" --> UniformSet["Uniform Set"]

        ActiveSet --> RoundSamples["Round Samples"]
        UniformSet --> RoundSamples

        RoundSamples --> Docking
    end
```
