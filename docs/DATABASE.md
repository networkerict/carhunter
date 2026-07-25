# Legacy Document

This document is preserved for historical reference.
Canonical, actively maintained documentation now lives in the new docs structure.
Start at [docs/README.md](README.md) for current operational and architecture guidance.

---

# AutoHunter Database Documentation

## Version

AutoHunter 2.7-dev

Database engine:

- SQLite


# 1. Overview

AutoHunter uses SQLite as its primary data store.

Each AutoHunter version has its own database.

Example:

/opt/carhunter/v2.6/carhunter.db

Production database

/opt/carhunter/v2.7-dev/carhunter.db

Development database


Database isolation is intentional to prevent development changes from affecting production.


# 2. Database Responsibilities

The database stores:

- Vehicle listings
- Vehicle specifications
- Descriptions
- Detected options
- Scores
- Ranking information
- Deal information
- Tracking information


# 3. Main Table

## cars

The main application table.

Each row represents one vehicle listing.


# 4. Vehicle Identification


## id

Internal database identifier.

Type:
INTEGER PRIMARY KEY


## autoscout_id

Original AutoScout24 listing identifier.

Used to:

- Detect existing vehicles
- Prevent duplicate imports


## fingerprint

Unique vehicle fingerprint.

Purpose:

- Detect duplicate listings
- Maintain vehicle identity


# 5. Vehicle Information


## title

Vehicle title from AutoScout24.


Example:

Audi A5 Cabriolet 45 TFSI quattro S line


## price

Current vehicle price.


## last_price

Previous known price.

Used for:

- Price change detection
- Price drop alerts


## year

Vehicle production year.


## km

Vehicle mileage.


## url

Original AutoScout24 listing URL.


# 6. Description Data


## description

Vehicle description text.

Used by:

- Option analysis
- Feature extraction
- Scoring


# 7. Option Analysis


## options_found

Detected vehicle equipment.

Example:
quattro
Matrix LED
Head-up display
Adaptive cruise control


## options_score

Calculated equipment value.


Example:
Matrix LED +10
quattro +15
Head-up display +10


# 8. Scoring Fields


## car_score

Vehicle quality score.

Based on:

- Engine
- Age
- Mileage
- Configuration


## value_score

Market value score.

Purpose:

Determine whether the asking price is attractive.


## final_score

Combined ranking score.

Used for:

- Ranking
- Recommendations


# 9. Deal Information


## deal_score

Additional opportunity score.

Used to identify exceptional listings.


## recommendation

Generated recommendation.

Examples:

Excellent match

Good candidate

Average


## alert

Notification status.

Used by:

- Telegram alerts
- Web dashboard


# 10. Tracking Fields


## first_seen

Date vehicle was first discovered.


## last_seen

Most recent database update.


Purpose:

Track:

- New listings
- Returning listings
- Price changes


# 11. Typical Data Flow

AutoScout24 listing
    |
    v
scraper.py
    |
    v
cars table
    |
    +----------------+
    |                |
    v                v
options.py         scoring.py
    |                |
    +----------------+

    |
    v
ranking / reports / alerts


# 12. Database Design Principles


AutoHunter follows:

- Keep production and development databases separated
- Avoid destructive migrations
- Prefer incremental schema changes
- Keep historical vehicle information
- Preserve scoring history where possible


# 13. Future Improvements


Possible future additions:

- Separate score history table
- Price history tracking
- Market comparison data
- User favorites
- Notification history
