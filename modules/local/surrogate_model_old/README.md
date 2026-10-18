# Surrogate Model

## Overview

Two stages, each using a fresh uniform random sample, docked, and used to train a model that scores and filters the population it was drawn from:

1. **Broad cut**: 1B → 10M (or 100M) via a regression surrogate
1. **Final cut**: 10M/100M → 1M via a calibrated binary classifier

## Stage 1: Broad Cut (1B → 10M/100M)

**Goal:** cheaply eliminate the bulk of clearly inactive compounds while preserving essentially all of the true actives, using a model that ranks rather than classifies.

1. Uniform random sample (~100K) from the full library
1. Dock the sample
1. Label: continuous regression target (flipped docking affinity, higher is better), no threshold applied
1. Assemble features for the sample
1. Train a regression surrogate (model family flexible)
1. Score the full library (or the physchem-filtered pool) with the trained regressor
1. Select survivors by top-fraction rank cut → 10M/100M

**Why regression here:** the model needs to produce a usable ranking across a population that's still enormous and highly imbalanced. A regression target uses the full continuous docking signal rather than collapsing everything below a threshold into a single "inactive" bucket, which matters most when the population is at its most imbalanced.

## Stage 2: Final Cut (10M/100M → 1M)

**Goal:** a defensible, statistically calibrated accept/reject decision on a much smaller, already-enriched population.

1. Fresh uniform random sample (~100K) drawn from Stage 1's survivors
1. Dock the sample
1. Freeze an active/inactive threshold from this sample's docking scores (e.g., 1st percentile)
1. Label: binary, using the frozen threshold
1. Assemble features
1. Train a binary classifier (model family flexible)
1. Calibrate via Mondrian conformal prediction (`crepes.WrapClassifier`, class-conditional)
1. Select survivors via conformal p-value threshold (or top-fraction rank cut, if a fixed output size is preferred) → target ~1M

**Why classification + calibration here:** the population is now small and enriched enough that a binary decision is meaningful, and a statistically guaranteed per-class error rate is a stronger, more defensible acceptance criterion than an arbitrary rank cut before committing the final population to full docking.

## Model family

Model family (GBDT / MLP / ensemble) is an independent, per-stage choice
