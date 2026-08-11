"""
Tests for ARCH-009 multi-source runtime components.

Tests cover:
- SourceInstance creation and validation
- SourceRegistry instance management
- SourceExecutionCoordinator dispatch and aggregation
- Execution result contracts with snapshots
- Error handling and isolation
- CRITICAL: Single acquisition per source (no duplicate ingestion)
- Integration with AutoScout24
"""

import pytest
from datetime import datetime
from typing import Optional

from sources.base import (
    DiscoveredListing,
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
from sources.coordinator import SourceExecutionCoordinator
from sources.registry import SourceRegistry
from sources.service import SourceIngestionService


def make_test_snapshot(source_name: str, listing_id: str) -> SourceSnapshot:
    """Helper to create test snapshots with required fields."""
    return SourceSnapshot(
        source_name=source_name,
        source_listing_id=listing_id,
        source_url="http://test.local/item",
        discovered_at=datetime.now(),
        fetched_at=datetime.now(),
        raw_summary_payload={},
        raw_detail_payload={},
        extracted_fields={},
        field_provenance={},
    )


# Mock source adapter for testing
class MockSourceAdapter:
    def __init__(self, name: str = "mock", should_fail: bool = False):
        self.name = name
        self.should_fail = should_fail
        self.call_count = 0
        self.acquire_call_count = 0

    def descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_name=self.name,
            display_name=f"Mock {self.name}",
            version="1.0.0",
            base_url="http://mock.local",
            plugin_descriptor=PluginDescriptor(
                plugin_id=self.name,
                plugin_family="mock",
                plugin_version="1.0.0",
                contract_version="1.0.0",
                display_name=f"Mock {self.name} Plugin",
                capabilities=["listing_discovery"],
                configuration_contract={},
            ),
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            supports_listing_discovery=True,
            supports_detail_fetch=False,
            supports_description_fetch=False,
            supports_full_inventory_scan=True,
        )

    def discover_listings(self, request, context) -> list[DiscoveredListing]:
        self.call_count += 1
        self.acquire_call_count += 1
        if self.should_fail:
            raise Exception(f"Mock {self.name} discover_listings failed")
        return []

    def fetch_listing_detail(self, listing, context) -> Optional[SourceListingDetail]:
        return None

    def fetch_description(self, listing, context) -> Optional[str]:
        return None

    def to_source_snapshot(self, listing, detail, description=None) -> SourceSnapshot:
        return make_test_snapshot(self.name, "mock-id")


class TestSourceInstance:
    """Test SourceInstance creation and properties."""

    def test_create_valid_instance(self):
        """Test creating a valid SourceInstance."""
        instance = SourceInstance(
            instance_id="test-instance",
            source_family="autoscout24",
            plugin_id="autoscout24",
            enabled=True,
            configuration={"max_pages": 100},
            provenance_identity="autoscout24.de",
        )
        assert instance.instance_id == "test-instance"
        assert instance.source_family == "autoscout24"
        assert instance.enabled is True
        assert instance.validation_state == "valid"

    def test_create_disabled_instance(self):
        """Test creating a disabled SourceInstance."""
        instance = SourceInstance(
            instance_id="test-instance",
            source_family="autoscout24",
            plugin_id="autoscout24",
            enabled=False,
            configuration={},
            provenance_identity="autoscout24.de",
        )
        assert instance.enabled is False


class TestSourceRegistry:
    """Test SourceRegistry functionality."""

    def test_register_plugin(self):
        """Test registering a source plugin."""
        registry = SourceRegistry()
        adapter = MockSourceAdapter("test")
        registry.register(adapter, enabled=True)
        assert registry.get("test") is adapter

    def test_register_instance(self):
        """Test registering a source instance."""
        registry = SourceRegistry()
        adapter = MockSourceAdapter("test")
        registry.register(adapter, enabled=True)

        instance = SourceInstance(
            instance_id="test-instance",
            source_family="test",
            plugin_id="test",
            enabled=True,
            configuration={},
            provenance_identity="test.local",
        )
        registry.register_instance(instance)
        assert registry.get_instance("test-instance") is instance

    def test_list_enabled_instances(self):
        """Test listing enabled instances."""
        registry = SourceRegistry()
        adapter = MockSourceAdapter("test")
        registry.register(adapter, enabled=True)

        instance1 = SourceInstance(
            instance_id="instance-1",
            source_family="test",
            plugin_id="test",
            enabled=True,
            configuration={},
            provenance_identity="test.local",
        )
        instance2 = SourceInstance(
            instance_id="instance-2",
            source_family="test",
            plugin_id="test",
            enabled=False,
            configuration={},
            provenance_identity="test.local",
        )

        registry.register_instance(instance1)
        registry.register_instance(instance2)

        enabled = registry.list_enabled_instances()
        assert len(enabled) == 1
        assert enabled[0].instance_id == "instance-1"


class TestSourceExecutionResult:
    """Test SourceExecutionResult with snapshots."""

    def test_success_result_with_snapshots(self):
        """Test creating a SUCCESS execution result with snapshots."""
        snapshot = make_test_snapshot("test", "test-1")
        result = SourceExecutionResult(
            source_instance_id="test",
            source_family="test",
            run_id="run-1",
            status="SUCCESS",
            snapshot_count=1,
            accepted_count=1,
            rejected_count=0,
            duration=1.5,
            snapshots=[snapshot],
            active_fingerprints=["fp-1"],
        )
        assert result.status == "SUCCESS"
        assert result.snapshot_count == 1
        assert len(result.snapshots) == 1
        assert len(result.active_fingerprints) == 1

    def test_failed_result_has_empty_snapshots(self):
        """Test that failed results have empty snapshot lists."""
        result = SourceExecutionResult(
            source_instance_id="test",
            source_family="test",
            run_id="run-1",
            status="FAILED",
            snapshot_count=0,
            accepted_count=0,
            rejected_count=0,
            duration=0.5,
            snapshots=[],
            active_fingerprints=[],
            error_category="SourceError",
            error_message="Connection failed",
        )
        assert result.status == "FAILED"
        assert result.snapshot_count == 0
        assert len(result.snapshots) == 0


class TestMultiSourceExecutionResult:
    """Test MultiSourceExecutionResult aggregation."""

    def test_aggregates_all_snapshots(self):
        """Test that aggregate result includes all snapshots from all sources."""
        snapshot1 = make_test_snapshot("test1", "test-1")
        snapshot2 = make_test_snapshot("test2", "test-2")

        result1 = SourceExecutionResult(
            source_instance_id="test-1",
            source_family="test",
            run_id="run-1",
            status="SUCCESS",
            snapshot_count=1,
            accepted_count=1,
            rejected_count=0,
            duration=1.0,
            snapshots=[snapshot1],
            active_fingerprints=["fp-1"],
        )
        result2 = SourceExecutionResult(
            source_instance_id="test-2",
            source_family="test",
            run_id="run-1",
            status="SUCCESS",
            snapshot_count=1,
            accepted_count=1,
            rejected_count=0,
            duration=1.5,
            snapshots=[snapshot2],
            active_fingerprints=["fp-2"],
        )

        aggregate = MultiSourceExecutionResult(
            run_id="run-1",
            per_instance_results=[result1, result2],
            total_snapshots=2,
            total_accepted=2,
            total_rejected=0,
            overall_outcome="SUCCESS",
            all_snapshots=[snapshot1, snapshot2],
            active_fingerprints=["fp-1", "fp-2"],
        )

        assert aggregate.overall_outcome == "SUCCESS"
        assert aggregate.total_snapshots == 2
        assert len(aggregate.all_snapshots) == 2
        assert len(aggregate.active_fingerprints) == 2

    def test_preserves_successful_snapshots_on_partial_failure(self):
        """Test that successful snapshots survive failure in another source."""
        snapshot_good = make_test_snapshot("good", "good-1")

        result_good = SourceExecutionResult(
            source_instance_id="good-instance",
            source_family="good",
            run_id="run-1",
            status="SUCCESS",
            snapshot_count=1,
            accepted_count=1,
            rejected_count=0,
            duration=1.0,
            snapshots=[snapshot_good],
            active_fingerprints=["fp-good"],
        )
        result_bad = SourceExecutionResult(
            source_instance_id="bad-instance",
            source_family="bad",
            run_id="run-1",
            status="FAILED",
            snapshot_count=0,
            accepted_count=0,
            rejected_count=0,
            duration=0.5,
            snapshots=[],
            active_fingerprints=[],
            error_message="Failed",
        )

        aggregate = MultiSourceExecutionResult(
            run_id="run-1",
            per_instance_results=[result_good, result_bad],
            total_snapshots=1,
            total_accepted=1,
            total_rejected=0,
            overall_outcome="PARTIAL_SUCCESS",
            all_snapshots=[snapshot_good],
            active_fingerprints=["fp-good"],
        )

        assert aggregate.overall_outcome == "PARTIAL_SUCCESS"
        assert aggregate.total_snapshots == 1
        assert len(aggregate.all_snapshots) == 1
        assert aggregate.all_snapshots[0].source_listing_id == "good-1"


class TestSourceExecutionCoordinator:
    """Test SourceExecutionCoordinator dispatch and aggregation."""

    def test_single_source_produces_snapshots(self):
        """Test that single source execution returns snapshots."""
        registry = SourceRegistry()
        adapter = MockSourceAdapter("test")
        registry.register(adapter, enabled=True)

        ingestion_service = SourceIngestionService(registry)
        coordinator = SourceExecutionCoordinator(registry, ingestion_service)

        instance = SourceInstance(
            instance_id="test-instance",
            source_family="test",
            plugin_id="test",
            enabled=True,
            configuration={},
            provenance_identity="test.local",
        )

        result = coordinator.execute_sources([instance])

        assert result.overall_outcome in ("SUCCESS", "PARTIAL_SUCCESS")
        assert len(result.per_instance_results) == 1
        assert result.per_instance_results[0].source_instance_id == "test-instance"
        # CRITICAL: snapshots are in result
        assert isinstance(result.all_snapshots, (list, tuple))

    def test_disabled_instance_no_acquisition(self):
        """Test that disabled instances are NOT acquired."""
        registry = SourceRegistry()
        adapter = MockSourceAdapter("test")
        registry.register(adapter, enabled=True)

        ingestion_service = SourceIngestionService(registry)
        coordinator = SourceExecutionCoordinator(registry, ingestion_service)

        instance = SourceInstance(
            instance_id="test-instance",
            source_family="test",
            plugin_id="test",
            enabled=False,
            configuration={},
            provenance_identity="test.local",
        )

        result = coordinator.execute_sources([instance])

        assert result.overall_outcome == "SKIPPED"
        assert result.per_instance_results[0].status == "SKIPPED_DISABLED"
        assert result.per_instance_results[0].snapshot_count == 0
        # CRITICAL: No acquisition happened
        assert adapter.acquire_call_count == 0

    def test_multiple_sources_acquire_each_once(self):
        """Test that multiple sources are acquired exactly once each."""
        registry = SourceRegistry()
        adapter1 = MockSourceAdapter("source1")
        adapter2 = MockSourceAdapter("source2")
        registry.register(adapter1, enabled=True)
        registry.register(adapter2, enabled=True)

        ingestion_service = SourceIngestionService(registry)
        coordinator = SourceExecutionCoordinator(registry, ingestion_service)

        instance1 = SourceInstance(
            instance_id="instance-1",
            source_family="source1",
            plugin_id="source1",
            enabled=True,
            configuration={},
            provenance_identity="source1.local",
        )
        instance2 = SourceInstance(
            instance_id="instance-2",
            source_family="source2",
            plugin_id="source2",
            enabled=True,
            configuration={},
            provenance_identity="source2.local",
        )

        result = coordinator.execute_sources([instance1, instance2])

        # CRITICAL: Each source acquired exactly once
        assert adapter1.acquire_call_count == 1
        assert adapter2.acquire_call_count == 1
        assert len(result.per_instance_results) == 2

    def test_one_source_fails_other_succeeds(self):
        """Test that one source failure doesn't prevent other sources from executing."""
        registry = SourceRegistry()
        adapter_good = MockSourceAdapter("good", should_fail=False)
        adapter_bad = MockSourceAdapter("bad", should_fail=True)
        registry.register(adapter_good, enabled=True)
        registry.register(adapter_bad, enabled=True)

        ingestion_service = SourceIngestionService(registry)
        coordinator = SourceExecutionCoordinator(registry, ingestion_service)

        instance_good = SourceInstance(
            instance_id="good-instance",
            source_family="good",
            plugin_id="good",
            enabled=True,
            configuration={},
            provenance_identity="good.local",
        )
        instance_bad = SourceInstance(
            instance_id="bad-instance",
            source_family="bad",
            plugin_id="bad",
            enabled=True,
            configuration={},
            provenance_identity="bad.local",
        )

        result = coordinator.execute_sources([instance_good, instance_bad])

        assert result.overall_outcome == "PARTIAL_SUCCESS"
        
        # Verify both were attempted
        good_result = [r for r in result.per_instance_results if r.source_instance_id == "good-instance"][0]
        bad_result = [r for r in result.per_instance_results if r.source_instance_id == "bad-instance"][0]
        
        assert good_result.status in ("SUCCESS", "PARTIAL_SUCCESS")
        assert bad_result.status == "FAILED"
        assert good_result.snapshot_count == len(good_result.snapshots)


class TestSingleAcquisition:
    """Test that each source is acquired EXACTLY ONCE per coordinator.execute_sources()."""

    def test_autoscout24_single_acquisition(self):
        """Test that AutoScout24 is not acquired multiple times."""
        from sources import build_default_source_registry, build_source_instances, build_source_coordinator
        
        registry = build_default_source_registry()
        as24_adapter = registry.get("autoscout24")
        original_discover = as24_adapter.discover_listings
        call_count = []
        
        def tracked_discover(request, context):
            call_count.append(1)
            return original_discover(request, context)
        
        as24_adapter.discover_listings = tracked_discover
        
        instances = build_source_instances(registry)
        coordinator = build_source_coordinator(registry)
        result = coordinator.execute_sources(instances)
        
        # CRITICAL: discover_listings called EXACTLY once
        assert len(call_count) == 1, f"Expected 1 acquisition, got {len(call_count)}"
        
        as24_adapter.discover_listings = original_discover

    def test_dry_run_single_acquisition(self):
        """Test that dry-run results in EXACTLY ONE acquisition per source."""
        registry = SourceRegistry()
        adapter = MockSourceAdapter("test")
        registry.register(adapter, enabled=True)

        ingestion_service = SourceIngestionService(registry)
        coordinator = SourceExecutionCoordinator(registry, ingestion_service)

        instance = SourceInstance(
            instance_id="test-instance",
            source_family="test",
            plugin_id="test",
            enabled=True,
            configuration={},
            provenance_identity="test.local",
        )

        result = coordinator.execute_sources([instance], dry_run=True)

        # CRITICAL: Even in dry-run, acquired exactly once
        assert adapter.acquire_call_count == 1
        assert result.per_instance_results[0].dry_run is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
