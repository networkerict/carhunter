# Legacy Document

This document is preserved for historical reference.
Canonical, actively maintained documentation now lives in the new docs structure.
Start at [docs/README.md](README.md) for current operational and architecture guidance.

---

# AutoHunter Architecture

## Version

AutoHunter 2.7-dev

Status: Development


# 1. Overview

AutoHunter is an automated vehicle discovery and analysis platform.

The application collects vehicle listings from AutoScout24, stores vehicle data, analyses specifications and equipment, calculates vehicle scores and identifies attractive purchase opportunities.

The primary use case is finding high-value Audi A5 Cabriolet vehicles based on:

- Vehicle configuration
- Engine type
- Age
- Mileage
- Equipment level
- Market value


# 2. Design Goals

AutoHunter is designed to:

- Automate vehicle searching
- Reduce manual marketplace monitoring
- Identify interesting vehicles quickly
- Rank vehicles based on configurable scoring logic
- Detect potential deals
- Provide notifications for interesting vehicles


# 3. High Level Architecture

             AutoScout24
                  |
                  |
                  v

             scraper.py

                  |
                  v

          +---------------+
          | SQLite        |
          | carhunter.db  |
          +---------------+

                  |
    +-------------+-------------+
    |             |             |
    v             v             v
    |             |             |

    +-------------+-------------+

                  |
                  v

          deal_score.py

                  |
      +-----------+-----------+
      |                       |
      v                       v

   webapp.py             telegram.py


# 4. Runtime Environment

Current environment:

- Linux server
- Proxmox virtual machine
- Python 3.12
- SQLite database


Filesystem:

opt/carhunter

├── v2.6
│ └── Production environment
│
├── v2.7-dev
│ └── Development environment
│
└── archive
└── Historical versions


# 5. Version Strategy


## AutoHunter 2.6

Production version.

Characteristics:

- Stable release
- Real usage
- Protected database
- Minimal changes


## AutoHunter 2.7-dev

Development version.

Characteristics:

- New features
- Testing environment
- Independent database
- Git controlled development


# 6. Application Workflow


The intended application workflow:

Scrape vehicles
|
v
Store/update database
|
v
Analyse descriptions
|
v
Analyse options
|
v
Calculate scores
|
v
Calculate deal score
|
v
Generate ranking
|
v
Reports / Web UI / Notifications


# 7. Main Components


## autohunter.py

Main application entry point.

Responsibilities:

- Command line interface
- Starting application functions
- Routing commands


Current commands:

- --pipeline
- --ranking
- --rescore
- --recheck
- --debug
- --debug-score


Future:

- Automated daily execution


---

## scraper.py

Responsible for collecting vehicle information.

Responsibilities:

- Connect to AutoScout24
- Extract listing data
- Parse vehicle information
- Create vehicle records


---

## database.py

Responsible for persistence.

Responsibilities:

- SQLite connection
- Database queries
- Insert/update vehicles
- Data retrieval


---

## models.py

Contains application data models.

Main object:

Car


Example attributes:

- title
- price
- year
- mileage
- description
- scores


---

## options.py

Vehicle equipment analysis.

Responsibilities:

- Detect options
- Calculate equipment score
- Store detected options


Examples:

- quattro
- Matrix LED
- Head-up display
- Adaptive cruise control


---

## scoring.py

Main vehicle scoring engine.

Responsibilities:

- Calculate vehicle quality score
- Calculate value score
- Combine scoring factors


Factors:

- Engine
- Year
- Mileage
- Equipment


---

## deal_score.py

Deal detection engine.

Responsibilities:

- Identify exceptional vehicles
- Compare vehicle attractiveness
- Generate recommendations


---

## pipeline.py

Automation workflow engine.

Purpose:

Provide a single execution flow for daily processing.


Planned workflow:
Scrape
|
Update
|
Analyse
|
Score
|
Rank
|
Notify


---

## webapp.py

Web interface.

Responsibilities:

- Display vehicles
- Show ranking
- Provide filtering


---

## telegram.py

Notification module.

Responsibilities:

- Send alerts
- Notify interesting vehicles


# 8. Development Principles


AutoHunter development follows:

- Production and development separation
- Database isolation
- Git version control
- Incremental feature development


# 9. Future Direction


Planned improvements:

- Automated daily pipeline
- Scheduler integration
- Improved ranking model
- Dashboard improvements
- AI assisted vehicle analysis
- Advanced notifications
