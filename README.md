# Lynceus

Named after the mythological figure renowned for extraordinary vision, reflecting the platform's goal of identifying transient conformations, cryptic interfaces, and corresponding actionable protein states.

**Lynceus** is a modular computational platform for discovering molecules that recognize specific protein conformational states and couple that recognition to a desired biological outcome.

## Motivation

Most ligand discovery pipelines treat a target protein as a single rigid structure - typically whatever conformation happens to be available from a crystal structure or a single predicted model. This is a poor approximation of reality. Proteins are dynamic ensembles: they sample multiple conformational substates, some only transiently, and a substantial fraction of biologically important recognition events (allosteric regulation, cryptic pocket opening, order-disorder transitions, conformational selection in signaling) depend on states that are rare, short-lived, or simply absent from static structural databases.

Lynceus is built around the premise that **conformational state is itself the design target**, not an afterthought to be handled by post-hoc induced-fit correction. The platform generates a representative ensemble of target states up front, screens against that ensemble (rather than a single structure), and uses a trained surrogate model to make ensemble-aware screening tractable at library scale. The outputs are candidates (small molecules, proteins, etc.) with an associated *state preference*, the information needed to couple binding to a specific functional or biological outcome (e.g., stabilizing an inactive state, blocking an interface that only forms transiently, or selectively engaging a disease-associated conformation over the wild-type/resting one).

## Architecture

```mermaid

flowchart TD

  subgraph Target
    RetrieveTargets[/"Retrieve Target(s)"/] --> Targets@{ shape: st-rect, label: "Targets" }
    Targets --> EnsembleGeneration{{"Target Ensemble Generation"}}
    EnsembleGeneration --> PutativeBindingSites@{shape: st-rect, label: "Putative Binding Sites"}
  end

  subgraph Candidate
    RetrieveCandidates[/"Retrieve Candidates"/] --> Candidates@{ shape: st-rect, label: "Candidates" }
    Candidates --> PhysioChemFilter{"Physiochemical Filter(s)<br>(PAINS, CNS-MPO, etc.)"}
    PhysioChemFilter --> PhysioChemFilteredCandidates@{shape: st-rect, label: "Filtered Candidates"}
  end

  subgraph Surrogate Model
    PhysioChemFilteredCandidates -- "sample" --> TrainingCandidates@{ shape: st-rect, label: "Training Candidates" }
    TrainingCandidates --> TrainingConformerGeneration{{"Training Conformer Generation"}}
    TrainingConformerGeneration --> TrainingConformers@{shape: st-rect, label: "Training Conformers"}

    TrainingConformers --> ModelComplexGeneration["Complex Generation"]
    PutativeBindingSites --> ModelComplexGeneration

    ModelComplexGeneration --> TrainingComplexes@{shape: st-rect, label: "Training Complexes"}

    TrainingComplexes --> TrainModel["Train Model"]
    TrainModel --> SurrogateModel@{shape: cyl, label: "Surrogate Model"}
  end

  subgraph Surrogate Model Filter
    SurrogateModel --> SurrogateModelFilter{"Model Filter"}
    PhysioChemFilteredCandidates -- "full library" --> SurrogateModelFilter
    SurrogateModelFilter --> SurrogateFilteredCandidates@{shape: st-rect, label: "Surrogate Filtered Candidates"}
  end

  subgraph Complex Generation
    SurrogateFilteredCandidates --> SurrogateFilteredCandidateConformerGeneration{{"Conformer Generation"}}
    SurrogateFilteredCandidateConformerGeneration --> CandidateConformers@{ shape: st-rect, label: "Candidate Conformers"}

    CandidateConformers --> ComplexGeneration["Complex Generation"]
    PutativeBindingSites --> ComplexGeneration

    ComplexGeneration --> Complexes@{shape: st-rect, label: "Complexes"}
  end

```
