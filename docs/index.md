# Lynceus

## Background

Most ligand discovery pipelines treat a target protein as a single rigid structure, typically whatever conformation happens to be available from a crystal structure or a single predicted model. In reality, proteins are dynamic ensembles. They sample multiple conformational substates, some only transiently, and many biologically important recognition events depend on states that are rare, short-lived, or absent from static structural databases. These include allosteric regulation, cryptic pocket opening, order-disorder transitions, and conformational selection in signaling.

## What Lynceus Is

Lynceus is a modular computational platform for discovering molecules that recognize specific protein conformational states and couple that recognition to a desired biological outcome.

The central premise is that **conformational state is itself the design target**, not an afterthought to be handled by post-hoc induced-fit correction.

## Goals

- **Treat the target as an ensemble.** Generate a representative set of target conformational states up front, and screen against that ensemble rather than a single structure.
- **Find sites that only exist in some states.** Detect binding sites across all ensemble members, including cryptic and transient pockets, and consolidate them into a distinct set of physical binding sites.
- **Support ultra-large virtual screening out of the box.** Train a surrogate model per binding site so that libraries of millions to billions of compounds can be screened against an ensemble of target states, with only a small fraction of the library needing to be docked.
- **Report state preference, not just affinity.** Produce candidates (small molecules, proteins, etc.) annotated with the conformational state they favor, which is the information needed to link binding to a functional outcome.
- **Stay modular.** Keep each stage (target ensemble generation, binding-site detection, candidate preprocessing and filtering, surrogate training, complex generation) independently replaceable and parallelizable.

## Intended Outcomes

Lynceus is designed to support state-selective discovery, such as:

- Stabilizing an inactive state of a target
- Blocking an interface that only forms transiently
- Selectively engaging a disease-associated conformation over the wild-type or resting one

## High-Level Workflow

1. **Target preparation:** Retrieve the target and generate a conformational ensemble.
1. **Binding-site discovery:** Detect binding sites on each ensemble member, then deduplicate them into a set of distinct sites, each tracking the members in which it appears.
1. **Candidate preparation:** Retrieve, preprocess, repartition, and apply physicochemical filters to the candidate library.
1. **Surrogate modeling (per site):** Sample candidates, generate training complexes, and train a surrogate model that predicts binding behavior for that site.
1. **Surrogate filtering (per site):** Apply the surrogate to the full filtered library to select promising candidates.
1. **Complex generation (per site):** Generate candidate conformers and build complexes against each binding site for downstream analysis.

From the binding-site stage onward, every step runs as an independent fan-out per deduplicated binding site rather than once per run.

## About the Name

Lynceus is named after the mythological figure renowned for extraordinary vision, reflecting the platform's goal of identifying transient conformations, cryptic interfaces, and the actionable protein states they represent.

## Status

Lynceus is in early-stage development (alpha). Features and APIs are unstable and subject to breaking changes, and it is not yet suitable for production use.
