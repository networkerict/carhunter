# Enterprise Data Repair Engine

The repair engine is a new subsystem for AutoHunter that can revisit incomplete vehicles and repair missing values by re-fetching the source listing.

## Usage

- Run a repair pass:
  - `python3 autohunter.py --repair`
- Preview repairs without writing anything:
  - `python3 autohunter.py --repair --dry-run`

## Behavior

The engine scans the database for incomplete cars and re-fetches the source URLs for those vehicles. It merges incoming data safely so existing good values are never overwritten by empty or lower-quality values.

## Notes

- The engine reuses the existing scraper layer.
- Repair results are stored in the `repair_runs` table.
- The Data Quality dashboard exposes repairable issues and repair history.

## Sample report

A sample report is available at [docs/repair_report_sample.txt](repair_report_sample.txt).
