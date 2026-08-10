from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

import config
import scraper

from .base import (
    DiscoveredListing,
    DiscoveryRequest,
    PluginDescriptor,
    SourceAdapter,
    SourceCapabilities,
    SourceContext,
    SourceDescriptor,
    SourceListingDetail,
    SourceSnapshot,
)


@dataclass
class AutoScout24SourceAdapter(SourceAdapter):
    max_pages: int = config.SOURCE_REGISTRY["autoscout24"]["max_pages"]

    def descriptor(self) -> SourceDescriptor:
        plugin_descriptor = PluginDescriptor(
            plugin_id="autoscout24",
            plugin_family="source",
            plugin_version=config.VERSION,
            contract_version="1.0",
            display_name="AutoScout24",
            capabilities=(
                "listing_discovery",
                "listing_detail",
                "description_fetch",
                "full_inventory_scan",
            ),
            configuration_contract={
                "required": [],
                "optional": ["enabled", "max_pages"],
            },
        )
        return SourceDescriptor(
            source_name="autoscout24",
            display_name="AutoScout24",
            version=config.VERSION,
            base_url="https://www.autoscout24.de",
            plugin_descriptor=plugin_descriptor,
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            supports_listing_discovery=True,
            supports_detail_fetch=True,
            supports_description_fetch=True,
            supports_full_inventory_scan=True,
            supports_structured_options=True,
        )

    def discover_listings(
        self, request: DiscoveryRequest, context: SourceContext
    ) -> list[DiscoveredListing]:
        max_pages = request.max_pages or self.max_pages
        discovered_at = datetime.now()
        listings_by_fingerprint: dict[str, DiscoveredListing] = {}

        for page in range(1, max_pages + 1):
            html = scraper.fetch_page(page)
            for raw_listing in scraper.parse_page(html):
                vehicle = raw_listing.get("vehicle", {})
                if vehicle.get("variant") != "Cabriolet":
                    continue

                listing_payload = deepcopy(raw_listing)
                fingerprint = scraper.create_fingerprint(listing_payload)
                listing_payload["fingerprint"] = fingerprint

                listings_by_fingerprint[fingerprint] = DiscoveredListing(
                    source_name=context.source_name,
                    source_listing_id=str(listing_payload.get("id") or ""),
                    source_url=f"{self.descriptor().base_url}{listing_payload['url']}",
                    discovered_at=discovered_at,
                    raw_summary_payload=listing_payload,
                )

        return list(listings_by_fingerprint.values())

    def fetch_listing_detail(
        self, listing: DiscoveredListing, context: SourceContext
    ) -> Optional[SourceListingDetail]:
        detail_payload = scraper.fetch_car_details(listing.source_url)
        if not detail_payload:
            return None

        return SourceListingDetail(
            source_name=context.source_name,
            source_listing_id=listing.source_listing_id,
            fetched_at=datetime.now(),
            raw_detail_payload=deepcopy(detail_payload),
        )

    def fetch_description(
        self, listing: DiscoveredListing, context: SourceContext
    ) -> Optional[str]:
        return scraper.fetch_description(listing.source_url)

    def to_source_snapshot(
        self,
        listing: DiscoveredListing,
        detail: Optional[SourceListingDetail],
        description: Optional[str] = None,
    ) -> SourceSnapshot:
        compatibility_payload = dict(listing.raw_summary_payload)
        detail_payload: Optional[Mapping[str, Any]] = None
        fetched_at = None

        if detail is not None:
            detail_payload = dict(detail.raw_detail_payload)
            compatibility_payload["detail"] = dict(detail.raw_detail_payload)
            fetched_at = detail.fetched_at

        extracted_fields = dict(scraper.normalize_car(compatibility_payload))
        if description is not None:
            extracted_fields["description"] = description

        field_provenance = self._build_field_provenance(
            extracted_fields=extracted_fields,
            description=description,
            source_listing_id=listing.source_listing_id,
        )

        return SourceSnapshot(
            source_name=listing.source_name,
            source_listing_id=listing.source_listing_id,
            source_url=listing.source_url,
            discovered_at=listing.discovered_at,
            fetched_at=fetched_at,
            raw_summary_payload=deepcopy(listing.raw_summary_payload),
            raw_detail_payload=deepcopy(detail_payload) if detail_payload is not None else None,
            extracted_fields=extracted_fields,
            field_provenance=field_provenance,
        )

    def _build_field_provenance(
        self,
        *,
        extracted_fields: Mapping[str, Any],
        description: Optional[str],
        source_listing_id: str,
    ) -> dict[str, dict[str, Any]]:
        provenance: dict[str, dict[str, Any]] = {}

        for field_name in extracted_fields:
            stage = "summary"
            if field_name == "description" and description is not None:
                stage = "description"

            provenance[field_name] = {
                "source_name": "autoscout24",
                "source_listing_id": source_listing_id,
                "stage": stage,
            }

        return provenance
