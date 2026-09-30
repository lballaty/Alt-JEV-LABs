# Agent instructions

Read `README.md` and `docs/EVALUATION.md` before changing model or benchmark behavior. The purpose is comparative evidence, not a favorable demonstration for any one model.

1. Do not fabricate benchmark numbers, model outputs, versions, API behavior, or test results. Distinguish verified upstream interfaces from code paths tested on this host.
2. Implement complete error handling and comments that explain the reasoning for junior contributors. No placeholder classes or silent fallbacks in a measured path.
3. Treat synthetic data as a harness fixture. Keep paired examples in one split, never train or calibrate on test, and label generated versus real datasets in every report.
4. Keep model calls local after explicit dependency/checkpoint downloads. Never commit weights, secrets, personal telemetry, or identifiable traces.
5. Do not enable agents or enforcement actions based on classifier output. A separate deterministic authorization and audit boundary is required for production use.
6. Work on a branch for follow-on changes, run focused tests, document hardware-dependent checks that were not run, and seek review before merging to main.
7. Preserve raw result provenance, including model ID, revision, software versions, hardware, seed, precision, prompt/template, scoring rubric and timing method.
8. If an upstream API differs, inspect its current primary documentation and fix the adapter. Do not mask a backend error as an incorrect prediction.
