from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import database

from sources.base import DiscoveredListing, SourceSnapshot


@dataclass(frozen=True)
class CompatibilityInventoryResult:
    new_cars: int
    not_available_anymore: int


def snapshot_to_compatibility_payload(snapshot: SourceSnapshot) -> dict:
    payload = dict(snapshot.extracted_fields)

    # Normalise mileage: legacy save_car reads "km"; some adapters emit "mileage".
    if payload.get("km") is None and payload.get("mileage") is not None:
        payload["km"] = payload["mileage"]

    # Normalise URL: legacy save_car reads "url"; inject from snapshot.source_url
    # when the adapter does not already include a "url" key.
    if not payload.get("url"):
        source_url = str(getattr(snapshot, "source_url", "") or "")
        if source_url:
            payload["url"] = source_url

    return payload


def should_fetch_detail_for_listing(listing: DiscoveredListing) -> bool:
    fingerprint = listing.raw_summary_payload.get("fingerprint")
    return not database.car_exists(fingerprint)


def apply_compatibility_inventory_updates(
    snapshots: Iterable[SourceSnapshot],
    active_fingerprints: Iterable[str],
    *,
    dry_run: bool = False,
) -> CompatibilityInventoryResult:
    snapshots = list(snapshots)
    active_fingerprints = [fingerprint for fingerprint in active_fingerprints if fingerprint]

    if dry_run:
        observed_fingerprints: set[str] = set()
        observed_autoscout_ids: set[str] = set()
        new_cars = 0

        for snapshot in snapshots:
            payload = snapshot_to_compatibility_payload(snapshot)
            autoscout_id = str(payload.get("id") or payload.get("autoscout_id") or "")
            fingerprint = str(payload.get("fingerprint") or "")

            exists = (
                (fingerprint and fingerprint in observed_fingerprints)
                or (autoscout_id and autoscout_id in observed_autoscout_ids)
                or _compatibility_record_exists(fingerprint, autoscout_id)
            )
            if not exists:
                new_cars += 1

            if fingerprint:
                observed_fingerprints.add(fingerprint)
            if autoscout_id:
                observed_autoscout_ids.add(autoscout_id)

        return CompatibilityInventoryResult(
            new_cars=new_cars,
            not_available_anymore=count_missing_cars_for_active_fingerprints(
                active_fingerprints
            ),
        )

    new_cars = 0
    for snapshot in snapshots:
        if database.save_car(snapshot_to_compatibility_payload(snapshot)):
            new_cars += 1

    not_available_anymore = database.mark_missing_cars_sold(active_fingerprints)
    return CompatibilityInventoryResult(
        new_cars=new_cars,
        not_available_anymore=not_available_anymore,
    )


def count_missing_cars_for_active_fingerprints(active_fingerprints: list[str]) -> int:
    connection = database.get_connection()
    try:
        if not active_fingerprints:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM cars
                WHERE COALESCE(sold, 0) = 0
                """
            ).fetchone()
        else:
            placeholders = ",".join(["?"] * len(active_fingerprints))
            row = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM cars
                WHERE fingerprint NOT IN ({placeholders})
                AND COALESCE(sold, 0) = 0
                """,
                active_fingerprints,
            ).fetchone()
        return row[0] if row else 0
    finally:
        connection.close()


def _compatibility_record_exists(fingerprint: str, autoscout_id: str) -> bool:
    connection = database.get_connection()
    try:
        row = connection.execute(
            """
            SELECT id
            FROM cars
            WHERE fingerprint = ?
            OR autoscout_id = ?
            ORDER BY id
            LIMIT 1
            """,
            (fingerprint, autoscout_id),
        ).fetchone()
        return row is not None
    finally:
        connection.close()
