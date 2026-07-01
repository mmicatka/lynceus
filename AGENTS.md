# AI Agent Guidelines for Lynceus

## Project Overview

- Stack: Python 3.13+, Dagster, `uv` (package management), `ruff` (lint/format), and DuckDB/Snowflake.
- Core Purpose: Data orchestration platform for ELT pipelines and analytics.
- Architecture: [docs/architecture.md](docs/architecture.md)
- Implementation Plan: [docs/implementation-plan](docs/implementation-plan.md)

## Architecture Rules

- Asset Definition: Always use `@asset` or `@multi_asset` decorators. Do not use legacy `@op` or `@graph` unless building dynamic loops.
- I/O Management: Separate compute from storage. Never hardcode file paths or credentials inside an asset; fetch them via Dagster Resources.
- Type Hints: Enforce strict Python type hinting for all asset inputs, outputs, and configuration objects.

## Critical Gotchas & Guardrails

- Environment Setup: Do not use `pip` or standard `venv`. Use `uv` commands for all environment manipulations.

- Database Access: DO NOT invoke raw database connections directly inside assets. Use Dagster Resources (`context.resources`).
- Memory Management: DO NOT load massive datasets into memory. Return `Output` with metadata, or stream chunked data.
- Schema Validation: Use `DagsterType` or Pydantic models to validate row schemas at the asset boundaries.

## Development & Run Commands

- Install environment & deps: `uv sync`
- Add a new dependency: `uv add <package_name>`
- Start UI (Dagster webserver): `uv run dagster dev`
- Materialize an asset locally: `uv run dagster asset materialize --select <asset_name>`
- Run unit tests: `uv run pytest`
- Lint, format, and check: `uv run ruff check` and `uv run ruff format`

## Code Formatting & Style

- Tooling: Exclusively use `ruff` for all formatting, sorting (`isort`), and lint rules.
- Compliance: Code must pass `ruff check --fix` and `ruff format` before any commit.
- Configuration: Define asset configurations using Dagster's `Config` class (Pydantic-backed environment variables).
- Metadata Logging: Always log row counts, execution times, or sample previews to the asset using `context.add_output_metadata`.

## Definition of Done

- Every new asset must have a corresponding unit test in `tests/` utilizing `materialize([new_asset])`.
- Code must include a comprehensive docstring describing data sources and transformations.
- The workspace must load into the Dagster UI without configuration or workspace schema errors.
