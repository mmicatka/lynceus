# Lynceus

Named after the mythological figure renowned for extraordinary vision, reflecting the platform's goal of identifying transient conformations, cryptic interfaces, and corresponding actionable protein states.

**Lynceus** is a modular computational platform for discovering molecules that recognize specific protein conformational states and couple that recognition to a desired biological outcome.

## Motivation

Most ligand discovery pipelines treat a target protein as a single rigid structure — typically whatever conformation happens to be available from a crystal structure or a single predicted model. This is a poor approximation of reality. Proteins are dynamic ensembles: they sample multiple conformational substates, some only transiently, and a substantial fraction of biologically important recognition events (allosteric regulation, cryptic pocket opening, order-disorder transitions, conformational selection in signaling) depend on states that are rare, short-lived, or simply absent from static structural databases.

Lynceus is built around the premise that **conformational state is itself the design target**, not an afterthought to be handled by post-hoc induced-fit correction. The platform generates a representative ensemble of target states up front, screens against that ensemble (rather than a single structure), and uses a trained surrogate model to make ensemble-aware screening tractable at library scale. The output is not just "molecules that bind" but molecules with an associated *state preference* — candidates annotated by which conformational substate(s) they recognize — which is the information needed to couple binding to a specific functional or biological outcome (e.g., stabilizing an inactive state, blocking an interface that only forms transiently, or selectively engaging a disease-associated conformation over the wild-type/resting one).

## Conceptual Overview

The platform is organized into four stages, each producing a well-defined intermediate output that feeds the next:

1. **Target** — define the protein(s) of interest and generate a structural ensemble representing their accessible conformational states.
1. **Recognizer** — define and pre-filter the candidate molecule library that will be screened against the target ensemble.
1. **Surrogate Model** — train a fast approximate model on a representative subsample of full target–candidate complexes, so the full library doesn't need to be exhaustively (and expensively) modeled against every target state.
1. **Ensemble Screening** — apply the trained surrogate to the full filtered library, then generate detailed conformers and complexes only for the subset that the surrogate model identifies as promising.

This staged design exists because the two most expensive operations in the pipeline — generating high-quality 3D conformers and generating/scoring target-candidate complexes — scale multiplicatively with library size and number of target states. The surrogate model stage exists specifically to avoid paying that multiplicative cost across the *entire* candidate library, reserving expensive, high-fidelity complex generation for a much smaller, pre-triaged set.

## Architecture

See [docs/architecture.md](docs/architecture.md)
