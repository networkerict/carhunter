from __future__ import annotations

import config

from .autoscout24 import AutoScout24SourceAdapter
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
from .registry import SourceRegistry
from .service import SourceIngestionResult, SourceIngestionService


def build_default_source_registry() -> SourceRegistry:
    registry = SourceRegistry()
    autoscout24_config = config.SOURCE_REGISTRY["autoscout24"]
    registry.register(
        AutoScout24SourceAdapter(max_pages=autoscout24_config["max_pages"]),
        configuration=autoscout24_config,
        enabled=autoscout24_config.get("enabled", True),
    )
    return registry


__all__ = [
    "AutoScout24SourceAdapter",
    "DiscoveredListing",
    "DiscoveryRequest",
    "PluginDescriptor",
    "SourceAdapter",
    "SourceCapabilities",
    "SourceContext",
    "SourceDescriptor",
    "SourceIngestionResult",
    "SourceIngestionService",
    "SourceListingDetail",
    "SourceRegistry",
    "SourceSnapshot",
    "build_default_source_registry",
]
