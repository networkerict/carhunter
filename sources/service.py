from __future__ import annotations

from dataclasses import dataclass, field

import database

from .base import DiscoveryRequest, SourceContext, SourceSnapshot
from .compatibility import snapshot_to_compatibility_payload
from .registry import SourceRegistry


@dataclass(frozen=True)
class SourceIngestionResult:
    source_name: str
    snapshots: list[SourceSnapshot] = field(default_factory=list)
    active_fingerprints: list[str] = field(default_factory=list)
    new_cars: int = 0
    not_available_anymore: int = 0


class SourceIngestionService:
    def __init__(self, registry: SourceRegistry) -> None:
        self._registry = registry

    def ingest_full_inventory(
        self, *, source_name: str, run_id: int | None = None, dry_run: bool = False
    ) -> SourceIngestionResult:
        entry = self._registry.get_entry(source_name)
        adapter = entry.adapter
        context = SourceContext(
            source_name=source_name,
            run_id=run_id,
            dry_run=dry_run,
            source_config=entry.configuration,
        )
        request = DiscoveryRequest(
            scan_mode="full_inventory",
            max_pages=entry.configuration.get("max_pages"),
            query_preset=entry.configuration.get("query_preset"),
        )

        discovered_listings = adapter.discover_listings(request, context)
        snapshots: list[SourceSnapshot] = []
        active_fingerprints: list[str] = []
        new_cars = 0

        for listing in discovered_listings:
            fingerprint = listing.raw_summary_payload.get("fingerprint")
            if fingerprint:
                active_fingerprints.append(fingerprint)

            detail = None
            if not database.car_exists(fingerprint):
                detail = adapter.fetch_listing_detail(listing, context)

            snapshot = adapter.to_source_snapshot(listing, detail)
            snapshots.append(snapshot)

            if database.save_car(snapshot_to_compatibility_payload(snapshot)):
                new_cars += 1

        not_available_anymore = database.mark_missing_cars_sold(active_fingerprints)
        return SourceIngestionResult(
            source_name=source_name,
            snapshots=snapshots,
            active_fingerprints=active_fingerprints,
            new_cars=new_cars,
            not_available_anymore=not_available_anymore,
        )
