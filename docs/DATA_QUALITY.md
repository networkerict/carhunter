# AutoHunter V3.0 Data Quality & Historical Migration

## Architecture

The data quality subsystem is implemented in [data_quality.py](../data_quality.py) and is designed as a reusable layer for historical backfill, dashboard reporting, and integrity checks.

## Backfill workflow

1. Select vehicles with missing specification fields.
2. Fetch current AutoScout24 details for each vehicle.
3. Only fill empty values.
4. Never overwrite existing valid values.
5. Support dry-run and resumable execution.

## Dashboard

The administration page renders the current database health, field coverage, and integrity issues.

## Integrity checks

The system classifies missing values as either expected optional fields or unexpected pipeline issues.

## How to run

- Run the backfill engine from Python:
  - `python3 - <<'PY'`
  - `import data_quality`
  - `engine = data_quality.BackfillEngine()`
  - `engine.run_backfill(limit=100, batch_size=20, dry_run=False)`

## Examples

- Dry run: `engine.run_backfill(..., dry_run=True)`
- Resume: `engine.run_backfill(..., resume=True)`

## Troubleshooting

- Inspect `logs/backfill_state.json` for resume state.
- Review `logs/autohunter.log` for detailed runtime messages.
