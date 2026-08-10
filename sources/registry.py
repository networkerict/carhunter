from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .base import SourceAdapter, SourceDescriptor, SourceUnavailableError


@dataclass(frozen=True)
class SourceRegistryEntry:
    adapter: SourceAdapter
    descriptor: SourceDescriptor
    configuration: Mapping[str, Any]
    enabled: bool = True


class SourceRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, SourceRegistryEntry] = {}

    def register(
        self,
        adapter: SourceAdapter,
        *,
        configuration: Mapping[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        descriptor = adapter.descriptor()
        if descriptor.source_name in self._entries:
            raise ValueError(f"Source already registered: {descriptor.source_name}")
        self._entries[descriptor.source_name] = SourceRegistryEntry(
            adapter=adapter,
            descriptor=descriptor,
            configuration=dict(configuration or {}),
            enabled=enabled,
        )

    def get(self, source_name: str) -> SourceAdapter:
        entry = self._entries.get(source_name)
        if entry is None or not entry.enabled:
            raise SourceUnavailableError(f"Unknown or disabled source: {source_name}")
        return entry.adapter

    def get_entry(self, source_name: str) -> SourceRegistryEntry:
        entry = self._entries.get(source_name)
        if entry is None or not entry.enabled:
            raise SourceUnavailableError(f"Unknown or disabled source: {source_name}")
        return entry

    def list_enabled(self) -> list[SourceRegistryEntry]:
        return [entry for entry in self._entries.values() if entry.enabled]
