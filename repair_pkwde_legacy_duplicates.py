#!/usr/bin/env python3
"""
CarHunter v3.0 — PKW.de Legacy Duplicate Repair
================================================
Soft-deletes the 61 pre-fix PKW.de cars rows that were created by the
first PKW.de pipeline run before the mileage/url compatibility fix.

Background
----------
The first PKW.de pipeline run (2026-08-14 ~17:55) called save_car()
without the mileage→km and source_url→url normalisations.  Every car
written by that run has:

  cars.url  = NULL
  cars.km   = NULL
  cars.fingerprint = NULL
  cars.autoscout_id = NULL

A subsequent post-fix run (2026-08-14 ~19:06) wrote correct rows for
the same PKW.de source_listings, with url and km populated.

This script identifies only provably duplicated rows (Category A) by
cross-referencing source_snapshots and matches each pre-fix car to its
correct post-fix replacement via (price, title) → source_listing_id →
source_url → cars.url.

Action taken: SET sold=1 (soft delete) on the pre-fix row only.
The post-fix replacement row is untouched.

Safety
------
* Defaults to dry-run.  Pass --execute to apply changes.
* Refuses rows that cannot be unambiguously matched (no spurious deletes).
* Idempotent: running twice changes nothing extra.
* Only touches cars that have url=NULL AND were created in the pre-fix batch.
* Never touches source_listings, source_snapshots, listings, vehicles, or
  listing_vehicle_mappings.
* Never touches AutoScout24 data.

Usage
-----
  python3 repair_pkwde_legacy_duplicates.py           # dry-run
  python3 repair_pkwde_legacy_duplicates.py --execute # apply
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

import database


# Timestamp range that identifies the pre-fix PKW.de pipeline run.
# All cars created in this window with url=NULL are candidates.
_PREFIX_RUN_TIMESTAMP_PREFIX = "2026-08-14T17:55"

# PKW.de source_id
_PKWDE_SOURCE_ID = 2


def _find_candidates(conn) -> list[dict]:
    """
    Return pre-fix cars that have a provable post-fix replacement.

    Strategy:
      1. Select cars with url=NULL created in the pre-fix run window.
      2. For each, find a PKW.de source_snapshot with matching (price, title).
      3. Resolve that snapshot → source_listing → source_url.
      4. Find the post-fix cars row with url = source_url.
      5. Only accept rows where exactly one pre-fix car and one post-fix car
         match, to avoid any ambiguity.
    """
    rows = conn.execute(
        """
        WITH prefix_cars AS (
            SELECT id, title, price, description, first_seen
            FROM cars
            WHERE first_seen LIKE ?
              AND (url IS NULL OR url = '')
              AND (fingerprint IS NULL OR fingerprint = '')
              AND (autoscout_id IS NULL OR autoscout_id = '')
        ),
        pkwde_snapshots AS (
            SELECT
                ss.source_listing_id,
                json_extract(ss.extracted_fields, '$.price') AS snap_price,
                json_extract(ss.extracted_fields, '$.title') AS snap_title,
                sl.source_url
            FROM source_snapshots ss
            JOIN source_listings sl
              ON sl.source_listing_id = ss.source_listing_id
             AND sl.source_id         = ss.source_id
            WHERE ss.source_id = ?
            GROUP BY ss.source_listing_id
        ),
        postfix_cars AS (
            SELECT id AS postfix_id, url AS postfix_url, km, price AS postfix_price
            FROM cars
            WHERE url LIKE 'https://suche.pkw.de/%'
        )
        SELECT
            p.id           AS prefix_car_id,
            p.title,
            p.price,
            pks.source_listing_id,
            pks.source_url,
            pf.postfix_id  AS postfix_car_id,
            pf.km          AS postfix_km
        FROM prefix_cars p
        JOIN pkwde_snapshots pks
          ON pks.snap_price = p.price
         AND pks.snap_title = p.title
        JOIN postfix_cars pf
          ON pf.postfix_url = pks.source_url
        ORDER BY p.id
        """,
        (_PREFIX_RUN_TIMESTAMP_PREFIX + "%", _PKWDE_SOURCE_ID),
    ).fetchall()
    return [
        {
            "prefix_car_id": r[0],
            "title": r[1],
            "price": r[2],
            "source_listing_id": r[3],
            "source_url": r[4],
            "postfix_car_id": r[5],
            "postfix_km": r[6],
        }
        for r in rows
    ]


def _check_for_ambiguity(candidates: list[dict]) -> list[dict]:
    """
    Reject any candidate where the same prefix_car_id or postfix_car_id
    appears more than once (title+price collision between different listings).
    Returns the unambiguous subset.
    """
    from collections import Counter

    prefix_counts = Counter(c["prefix_car_id"] for c in candidates)
    postfix_counts = Counter(c["postfix_car_id"] for c in candidates)

    clean = []
    ambiguous = []
    for c in candidates:
        if prefix_counts[c["prefix_car_id"]] > 1 or postfix_counts[c["postfix_car_id"]] > 1:
            ambiguous.append(c)
        else:
            clean.append(c)
    return clean, ambiguous


def run(*, execute: bool = False) -> int:
    conn = database.get_connection()

    try:
        # Ensure repair_runs table exists (may not be present in test DBs)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS repair_runs "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, report TEXT)"
        )
        conn.commit()

        candidates = _find_candidates(conn)
        clean, ambiguous = _check_for_ambiguity(candidates)

        total_prefix = conn.execute(
            "SELECT COUNT(*) FROM cars WHERE first_seen LIKE ? AND (url IS NULL OR url='')",
            (_PREFIX_RUN_TIMESTAMP_PREFIX + "%",)
        ).fetchone()[0]

        print("=" * 60)
        print("PKW.de Legacy Duplicate Repair")
        print("Mode:", "EXECUTE" if execute else "DRY-RUN")
        print("=" * 60)
        print(f"Pre-fix candidate rows (url=NULL, 17:55 batch): {total_prefix}")
        print(f"Category A — provable replacements found:       {len(clean)}")
        print(f"Category D — ambiguous (same title+price):      {len(ambiguous)}")
        print(f"Category C — no replacement found:              {total_prefix - len(clean) - len(ambiguous)}")
        print()

        if ambiguous:
            print("AMBIGUOUS rows (will NOT be touched):")
            for c in ambiguous:
                print(f"  prefix={c['prefix_car_id']} postfix={c['postfix_car_id']} title={c['title']!r} price={c['price']}")
            print()

        print("Category A detail:")
        for c in clean:
            sold_already = conn.execute(
                "SELECT sold FROM cars WHERE id=?", (c["prefix_car_id"],)
            ).fetchone()
            already = sold_already and sold_already[0] == 1
            status = "ALREADY SOFT-DELETED" if already else ("WILL SOFT-DELETE" if not execute else "SOFT-DELETING")
            print(
                f"  prefix_car={c['prefix_car_id']:5d} → postfix_car={c['postfix_car_id']:5d}"
                f"  listing={c['source_listing_id']}"
                f"  price={c['price']}  km={c['postfix_km']}"
                f"  [{status}]"
            )

        print()

        if not execute:
            print("DRY-RUN complete. No changes made.")
            print("Run with --execute to apply.")
            return 0

        # Apply soft-delete
        now = datetime.now().isoformat()
        changed = 0
        for c in clean:
            result = conn.execute(
                """
                UPDATE cars
                SET sold = 1,
                    sold_at = ?,
                    recommendation = 'superseded_by_prefix_fix'
                WHERE id = ?
                  AND (sold IS NULL OR sold = 0)
                """,
                (now, c["prefix_car_id"]),
            )
            if result.rowcount > 0:
                changed += 1

        conn.commit()

        print(f"Applied: {changed} rows soft-deleted (sold=1).")
        if changed < len(clean):
            print(f"  ({len(clean) - changed} were already soft-deleted)")

        # Log to repair_runs
        report = {
            "repair": "pkwde_legacy_duplicates",
            "executed_at": now,
            "total_prefix_candidates": total_prefix,
            "category_a": len(clean),
            "category_d_ambiguous": len(ambiguous),
            "rows_changed": changed,
        }
        conn.execute(
            "INSERT INTO repair_runs (created_at, report) VALUES (?, ?)",
            (now, json.dumps(report)),
        )
        conn.commit()
        print("Repair logged to repair_runs.")
        return 0

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes. Without this flag the script runs in dry-run mode.",
    )
    args = parser.parse_args()
    sys.exit(run(execute=args.execute))


if __name__ == "__main__":
    main()
