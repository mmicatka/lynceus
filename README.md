# Lynceus

![Project Status: Work in Progress](https://img.shields.io/badge/status-WIP-yellow)
[![Documentation](https://img.shields.io/badge/docs-lynceus-blue)](https://mmicatka.github.io/lynceus/)

> [!WARNING]
> **Active Development / Work in Progress**
> This project is currently in early-stage development (**Alpha**). Features and APIs are unstable and subject to breaking changes without notice. **Not suitable for production use yet.**

## Documentation

Full documentation—including project overview, system architecture, usage guides, and results—is available at **[mmicatka.github.io/lynceus](https://mmicatka.github.io/lynceus/)**.

## Development Environment

To test these workflows, you need an existing Kubernetes cluster (like k3s, minikube, or kind) with Argo Workflows installed.

If you don't have Argo set up yet, you can use the included helper script:

```bash
cd scripts/setup-argo
cp .env.example .env
make all
