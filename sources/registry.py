from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from .base import (
    SourceAdapter,
    SourceDescriptor,
    SourceInstance,
    SourceUnavailableError,
)


@dataclass(frozen=True)
class SourceRegistryEntry:
    adapter: SourceAdapter
    descriptor: SourceDescriptor
    configuration: Mapping[str, Any]
    enabled: bool = True


class SourceRegistry:
    def __init__(self) -> None:
        self._plugin_entries: dict[str, SourceRegistryEntry] = {}
        self._source_instances: dict[str, SourceInstance] = {}

    def register(
        self,
        adapter: SourceAdapter,
        *,
        configuration: Mapping[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        descriptor = adapter.descriptor()
        if descriptor.source_name in self._plugin_entries:
            raise ValueError(f"Source already registered: {descriptor.source_name}")
        self._plugin_entries[descriptor.source_name] = SourceRegistryEntry(
            adapter=adapter,
            descriptor=descriptor,
            configuration=dict(configuration or {}),
            enabled=enabled,
        )

    def register_instance(
        self,
        instance: SourceInstance,
    ) -> None:
        """Register a source instance for multi-source execution."""
        if instance.instance_id in self._source_instances:
            raise ValueError(f"Instance already registered: {instance.instance_id}")
        # Verify the plugin is registered
        if instance.source_family not in self._plugin_entries:
            raise ValueError(
                f"Plugin not registered for family: {instance.source_family}"
            )
        self._source_instances[instance.instance_id] = instance

    def get(self, source_name: str) -> SourceAdapter:
        entry = self._plugin_entries.get(source_name)
        if entry is None or not entry.enabled:
            raise SourceUnavailableError(f"Unknown or disabled source: {source_name}")
        return entry.adapter

    def get_entry(self, source_name: str) -> SourceRegistryEntry:
        entry = self._plugin_entries.get(source_name)
        if entry is None or not entry.enabled:
            raise SourceUnavailableError(f"Unknown or disabled source: {source_name}")
        return entry

    def get_instance(self, instance_id: str) -> Optional[SourceInstance]:
        """Retrieve a source instance by ID."""
        return self._source_instances.get(instance_id)

    def list_enabled(self) -> list[SourceRegistryEntry]:
        return [entry for entry in self._plugin_entries.values() if entry.enabled]

    def list_instances(self) -> Sequence[SourceInstance]:
        """List all registered source instances."""
        return list(self._source_instances.values())

    def list_enabled_instances(self) -> Sequence[SourceInstance]:
        """List all enabled source instances."""
        return [inst for inst in self._source_instances.values() if inst.enabled]
