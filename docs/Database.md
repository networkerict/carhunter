# Database

## Strategy
- SQLite per environment directory.
- Active DB path resolved from `config.DATABASE` relative to app directory.

## Active Databases
- Production: `/opt/carhunter/v2.9/carhunter.db`
- Development: `/opt/carhunter/v3.0-dev/carhunter.db`

## Promotion Rule
For v2.9 promotion, the development database was promoted as production baseline.

## Safety Controls
- Pre-release schema checks (`PRAGMA table_info(cars)`)
- Integrity checks on core score columns
- Duplicate AutoScout ID checks
- Price/year sanity checks

## Operational Notes
- Never assume DB by filename alone from another directory.
- Always validate database path using environment directory and/or `current` symlink.
