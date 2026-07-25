# Architecture

## Runtime Topology
- Production code: `/opt/carhunter/v2.9`
- Production alias: `/opt/carhunter/current`
- Development code: `/opt/carhunter/v3.0-dev`
- Database model: SQLite file per environment directory (`carhunter.db`)

## Layers
- Entry points: CLI (`autohunter.py`), Web (`webapp.py`)
- Orchestration: `orchestration.py`
- Domain logic: scraping, options, scoring, deals, watchlist, recommendations
- Persistence: `database.py`
- Reporting/notifications: dashboard/reporting/telegram

## Service Separation
- Production web service: `autohunter-web.service` (port 5000)
- Development web service: `autohunter-web-dev.service` (port 5001)
- Production pipeline scheduler: `autohunter-pipeline.timer` -> `autohunter-pipeline.service`

## Deployment Principles
- Symlink-controlled production (`current`)
- Immutable version directories per release
- Explicit promotion from development to production
