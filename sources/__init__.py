from __future__ import annotations

import config

from .autoscout24 import AutoScout24SourceAdapter
from .mobile_de import MobileDeSourceAdapter
from .base import (
    DiscoveredListing,
    DiscoveryRequest,
    MultiSourceExecutionResult,
    PluginDescriptor,
    SourceAdapter,
    SourceCapabilities,
    SourceContext,
    SourceDescriptor,
    SourceExecutionResult,
    SourceInstance,
    SourceListingDetail,
    SourceSnapshot,
)
from .coordinator import SourceExecutionCoordinator
from .registry import SourceRegistry
from .service import SourceIngestionResult, SourceIngestionService


def build_default_source_registry() -> SourceRegistry:
    registry = SourceRegistry()
    
    # Register AutoScout24
    autoscout24_config = config.SOURCE_REGISTRY.get("autoscout24", {})
    if autoscout24_config:
        registry.register(
            AutoScout24SourceAdapter(max_pages=autoscout24_config.get("max_pages", 100)),
            configuration=autoscout24_config,
            enabled=autoscout24_config.get("enabled", True),
        )
    
    # Register Mobile.de
    mobile_de_config = config.SOURCE_REGISTRY.get("mobile_de", {})
    if mobile_de_config:
        registry.register(
            MobileDeSourceAdapter(
                max_pages=mobile_de_config.get("max_pages", 10),
                page_size=mobile_de_config.get("page_size", 50),
            ),
            configuration=mobile_de_config,
            enabled=mobile_de_config.get("enabled", True),
        )
    
    return registry


def build_source_instances(registry: SourceRegistry) -> list[SourceInstance]:
    """Build source instances from configuration."""
    instances = []
    for instance_id, instance_config in config.SOURCE_INSTANCES.items():
        source_family = instance_config.get("source_family")
        plugin_id = instance_config.get("plugin_id")
        enabled = instance_config.get("enabled", True)
        provenance_identity = instance_config.get("provenance_identity", instance_id)

        # Validate that the source family is registered
        try:
            registry.get(source_family)
        except Exception as e:
            raise ValueError(
                f"Source family '{source_family}' not registered: {e}"
            )

        instance = SourceInstance(
            instance_id=instance_id,
            source_family=source_family,
            plugin_id=plugin_id,
            enabled=enabled,
            configuration=instance_config,
            provenance_identity=provenance_identity,
            validation_state="valid",
        )
        instances.append(instance)
        registry.register_instance(instance)

    return instances


def build_source_coordinator(registry: SourceRegistry) -> SourceExecutionCoordinator:
    """Build the source execution coordinator."""
    ingestion_service = SourceIngestionService(registry)
    return SourceExecutionCoordinator(registry, ingestion_service)


__all__ = [
    "AutoScout24SourceAdapter",
    "MobileDeSourceAdapter",
    "DiscoveredListing",
    "DiscoveryRequest",
    "MultiSourceExecutionResult",
    "PluginDescriptor",
    "SourceAdapter",
    "SourceCapabilities",
    "SourceContext",
    "SourceDescriptor",
    "SourceExecutionCoordinator",
    "SourceExecutionResult",
    "SourceIngestionResult",
    "SourceIngestionService",
    "SourceInstance",
    "SourceListingDetail",
    "SourceRegistry",
    "SourceSnapshot",
    "build_default_source_registry",
    "build_source_coordinator",
    "build_source_instances",
]
