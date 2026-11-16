# Lynceus

![Project Status: Work in Progress](https://img.shields.io/badge/status-WIP-yellow)

> [!WARNING]
> **Active Development / Work in Progress**
> This project is currently in early-stage development (**Alpha**). Features and APIs are unstable and subject to breaking changes without notice. **Not suitable for production use yet.**
> Major refactor in progress

## Overview

Named after the mythological figure renowned for extraordinary vision, reflecting the platform's goal of identifying transient conformations, cryptic interfaces, and corresponding actionable protein states.

**Lynceus** is a modular computational platform for discovering molecules that bind to specific protein conformational states.

## Motivation

Most ligand discovery pipelines treat a target protein as a single rigid structure - typically whatever conformation happens to be available from a crystal structure or a single predicted model. This is a poor approximation of reality. Proteins are dynamic ensembles: they sample multiple conformational substates, some only transiently, and a substantial fraction of biologically important recognition events (allosteric regulation, cryptic pocket opening, order-disorder transitions, conformational selection in signaling) depend on states that are rare, short-lived, or simply absent from static structural databases.

Lynceus is built around the premise that **conformational state is itself the design target**, not an afterthought to be handled by post-hoc induced-fit correction. The platform generates a representative ensemble of target states up front, screens against that ensemble (rather than a single structure), and uses a trained surrogate model to make ensemble-aware screening tractable at library scale. The outputs are candidates (small molecules, proteins, etc.) with an associated *state preference*, the information needed to couple binding to a specific functional or biological outcome (e.g., stabilizing an inactive state, blocking an interface that only forms transiently, or selectively engaging a disease-associated conformation over the wild-type/resting one).

## Architecture

See [architecture.md](docs/architecture.md)

## Development Environment

To test these workflows, you need an existing Kubernetes cluster (like k3s, minikube, or kind) with Argo Workflows installed.

If you don't have Argo set up yet, you can use the included helper script:

```bash
cd scripts/setup-argo
cp .env.example .env
make all
```
