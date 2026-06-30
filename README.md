# Lynceus

Named after the mythological figure renowned for extraordinary vision, reflecting the platform's goal of identifying transient conformations, cryptic interfaces, and corresponding actionable protein states.

**Lynceus** is a modular computational platform for discovering molecules that recognize specific protein conformational states and couple that recognition to a desired biological outcome.

## High-Level Architecture

```mermaid

flowchart TD

  subgraph Target
    direction TD

    RetrieveTargets[/"Retrieve Target(s)"/] --> Targets@{ shape: st-rect, label: "Targets" }
    Targets --> EnsembleGeneration{{"Target Ensemble Generation"}}
    EnsembleGeneration --> TargetSurfaces@{shape: st-rect, label: "Target Surfaces"}
  end

  subgraph Recognizer
    direction TD

    IngestCandidates[/"Retrieve Candidates"/] --> RecognizerCandidates@{ shape: st-rect, label: "Candidates" }
    RecognizerCandidates --> InitialFilter{"Physiochemical Filter(s)<br>(PAINS, CNS-MPO, etc.)"}
    InitialFilter --> FilteredCandidates@{shape: st-rect, label: "Filtered Candidates"}
  end

  subgraph Surrogate Model
    direction TD

    FilteredCandidates -- "sample" --> TrainingCandidates@{ shape: st-rect, label: "Training Candidates" }
    TrainingCandidates --> TrainingConformerGeneration{{"Training Conformer Generation"}}
    TrainingConformerGeneration --> TrainingConformers@{shape: st-rect, label: "Training Conformers"}

    TrainingConformers --> ModelComplexGeneration["Complex Generation"]
    TargetSurfaces --> ModelComplexGeneration

    ModelComplexGeneration --> TrainingComplexes@{shape: st-rect, label: "Training Complexes"}

    TrainingComplexes --> TrainModel["Train Model"]
    TrainModel --> SurrogateModel@{shape: cyl, label: "Surrogate Model"}
  end

  SurrogateModel --> SurrogateModelFilter{"Model Filter"}
  
  FilteredCandidates -- "full library" --> SurrogateModelFilter

  SurrogateModelFilter --> MLFilteredCandidates@{shape: st-rect, label: "Filtered Candidate"}

  MLFilteredCandidates --> MLFilteredCandidateConformerGeneration{{"Conformer Generation"}}

  MLFilteredCandidateConformerGeneration --> MLFilteredCandidateConformers@{ shape: st-rect, label: "Candidate Conformers"}

  MLFilteredCandidateConformers --> ComplexGeneration["Complex Generation"]
  TargetSurfaces --> ComplexGeneration

  ComplexGeneration --> Complexes@{shape: st-rect, label: "Complexes"}

```
