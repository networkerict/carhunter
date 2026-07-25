# Pipeline

## Canonical Orchestration
All mutable processing paths route through `orchestration.run_pipeline(...)` with mode-specific stages.

## Main Modes
- `full`: scrape -> descriptions -> options -> scores -> deal scores -> notifications -> stats -> cleanup
- `rescore`: options (forced refresh) -> scores -> deal scores
- `options`, `descriptions`, `repair`, `recheck`: targeted modes

## Why It Matters
- Prevents drift between CLI, Web, and maintenance entrypoints.
- Ensures consistent score and notification order.
