from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .base import DiscoveredListing, DiscoveryRequest, SourceContext, SourceSnapshot
from .registry import SourceRegistry


@dataclass(frozen=True)
class SourceIngestionResult:
    source_name: str
    snapshots: list[SourceSnapshot] = field(default_factory=list)
    active_fingerprints: list[str] = field(default_factory=list)


class SourceIngestionService:
    def __init__(self, registry: SourceRegistry) -> None:
        self._registry = registry

    def ingest_full_inventory(
        self,
        *,
        source_name: str,
        should_fetch_detail: Callable[[DiscoveredListing], bool] | None = None,
    ) -> SourceIngestionResult:
        entry = self._registry.get_entry(source_name)
        adapter = entry.adapter
        context = SourceContext(source_name=source_name)
        request = DiscoveryRequest(
            scan_mode="full_inventory",
            max_pages=entry.configuration.get("max_pages"),
        )

        discovered_listings = adapter.discover_listings(request, context)
        snapshots: list[SourceSnapshot] = []
        active_fingerprints: list[str] = []

        for listing in discovered_listings:
            fingerprint = listing.raw_summary_payload.get("fingerprint")
            if fingerprint:
                active_fingerprints.append(fingerprint)

            detail = None
            if should_fetch_detail is None or should_fetch_detail(listing):
                detail = adapter.fetch_listing_detail(listing, context)

            snapshot = adapter.to_source_snapshot(listing, detail)
            snapshots.append(snapshot)

        return SourceIngestionResult(
            source_name=source_name,
            snapshots=snapshots,
            active_fingerprints=active_fingerprints,
        )
