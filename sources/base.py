from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class PluginDescriptor:
    plugin_id: str
    plugin_family: str
    plugin_version: str
    contract_version: str
    display_name: str
    capabilities: Sequence[str]
    configuration_contract: Mapping[str, Any]
    dependencies: Sequence[str] = field(default_factory=tuple)
    optional_capabilities: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceDescriptor:
    source_name: str
    display_name: str
    version: str
    base_url: str
    plugin_descriptor: PluginDescriptor


@dataclass(frozen=True)
class SourceCapabilities:
    supports_listing_discovery: bool
    supports_detail_fetch: bool
    supports_description_fetch: bool
    supports_full_inventory_scan: bool
    supports_incremental_sync: bool = False
    supports_explicit_sold_status: bool = False
    supports_structured_options: bool = False
    supports_rate_limit_headers: bool = False


@dataclass(frozen=True)
class DiscoveryRequest:
    scan_mode: str = "full_inventory"
    max_pages: Optional[int] = None


@dataclass(frozen=True)
class SourceContext:
    source_name: str


@dataclass(frozen=True)
class DiscoveredListing:
    source_name: str
    source_listing_id: str
    source_url: str
    discovered_at: datetime
    raw_summary_payload: Mapping[str, Any]


@dataclass(frozen=True)
class SourceListingDetail:
    source_name: str
    source_listing_id: str
    fetched_at: datetime
    raw_detail_payload: Mapping[str, Any]


@dataclass(frozen=True)
class SourceSnapshot:
    source_name: str
    source_listing_id: str
    source_url: str
    discovered_at: datetime
    fetched_at: Optional[datetime]
    raw_summary_payload: Mapping[str, Any]
    raw_detail_payload: Optional[Mapping[str, Any]]
    extracted_fields: Mapping[str, Any]
    field_provenance: Mapping[str, Mapping[str, Any]]


class SourceError(Exception):
    pass


class SourceUnavailableError(SourceError):
    pass


class SourceContractError(SourceError):
    pass


@runtime_checkable
class SourceAdapter(Protocol):
    def descriptor(self) -> SourceDescriptor:
        ...

    def capabilities(self) -> SourceCapabilities:
        ...

    def discover_listings(
        self, request: DiscoveryRequest, context: SourceContext
    ) -> list[DiscoveredListing]:
        ...

    def fetch_listing_detail(
        self, listing: DiscoveredListing, context: SourceContext
    ) -> Optional[SourceListingDetail]:
        ...

    def fetch_description(
        self, listing: DiscoveredListing, context: SourceContext
    ) -> Optional[str]:
        ...

    def to_source_snapshot(
        self,
        listing: DiscoveredListing,
        detail: Optional[SourceListingDetail],
        description: Optional[str] = None,
    ) -> SourceSnapshot:
        ...


@dataclass(frozen=True)
class SourceInstance:
    instance_id: str
    source_family: str
    plugin_id: str
    enabled: bool
    configuration: Mapping[str, Any]
    provenance_identity: str
    validation_state: str = "valid"


@dataclass(frozen=True)
class SourceExecutionResult:
    source_instance_id: str
    source_family: str
    run_id: Optional[str]
    status: str
    snapshot_count: int
    accepted_count: int
    rejected_count: int
    duration: float
    snapshots: Sequence[SourceSnapshot] = field(default_factory=tuple)
    active_fingerprints: Sequence[str] = field(default_factory=tuple)
    error_category: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    dry_run: bool = False


@dataclass(frozen=True)
class MultiSourceExecutionResult:
    run_id: Optional[str]
    per_instance_results: Sequence[SourceExecutionResult]
    total_snapshots: int
    total_accepted: int
    total_rejected: int
    overall_outcome: str
    all_snapshots: Sequence[SourceSnapshot] = field(default_factory=tuple)
    active_fingerprints: Sequence[str] = field(default_factory=tuple)
