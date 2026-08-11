"""
SourceExecutionCoordinator - Multi-source dispatch and isolation layer.

This coordinator implements the ARCH-008 multi-source integration boundary.
It is responsible for:
- selecting enabled source instances
- dispatching each instance independently
- isolating failures between instances
- aggregating results with snapshots

It is NOT responsible for:
- scheduling/orchestration (ARCH-004)
- canonical persistence (ARCH-007)
- plugin implementation details
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from .base import (
    MultiSourceExecutionResult,
    SourceError,
    SourceExecutionResult,
    SourceInstance,
    SourceSnapshot,
)
from .registry import SourceRegistry
from .service import SourceIngestionService


class SourceExecutionCoordinator:
    def __init__(
        self,
        registry: SourceRegistry,
        ingestion_service: Optional[SourceIngestionService] = None,
    ) -> None:
        self._registry = registry
        self._ingestion_service = ingestion_service or SourceIngestionService(registry)

    def execute_sources(
        self,
        source_instances: Sequence[SourceInstance],
        run_id: Optional[str] = None,
        dry_run: bool = False,
        should_fetch_detail=None,
    ) -> MultiSourceExecutionResult:
        """
        Execute multiple source instances and aggregate results with snapshots.

        Each instance is executed independently. Failure in one instance
        does not block or invalidate results from other instances.

        Args:
            source_instances: List of SourceInstance objects to execute
            run_id: Optional run identifier for tracking
            dry_run: If True, acquire/parse/map but don't persist
            should_fetch_detail: Optional callable to filter detail fetches

        Returns:
            MultiSourceExecutionResult with per-instance results, aggregated counts,
            and all acquired snapshots (never erased by failures)
        """
        per_instance_results = []
        total_snapshots = 0
        total_accepted = 0
        total_rejected = 0
        all_snapshots = []
        all_fingerprints = []

        for instance in source_instances:
            result = self._execute_source_instance(
                instance,
                run_id,
                dry_run,
                should_fetch_detail,
            )
            per_instance_results.append(result)
            total_snapshots += result.snapshot_count
            total_accepted += result.accepted_count
            total_rejected += result.rejected_count
            all_snapshots.extend(result.snapshots)
            all_fingerprints.extend(result.active_fingerprints)

        # Determine overall outcome
        # One source failure does NOT make the entire run fail
        # Only set to FAILED if all sources failed or all were skipped
        failed_count = sum(
            1 for r in per_instance_results if r.status == "FAILED"
        )
        skipped_count = sum(
            1
            for r in per_instance_results
            if r.status in ("SKIPPED_DISABLED", "SKIPPED_INVALID_CONFIGURATION")
        )
        successful_count = sum(
            1
            for r in per_instance_results
            if r.status in ("SUCCESS", "PARTIAL_SUCCESS")
        )

        if successful_count > 0:
            if failed_count > 0 or skipped_count > 0:
                overall_outcome = "PARTIAL_SUCCESS"
            else:
                overall_outcome = "SUCCESS"
        elif failed_count > 0:
            overall_outcome = "FAILED"
        else:
            overall_outcome = "SKIPPED"

        return MultiSourceExecutionResult(
            run_id=run_id,
            per_instance_results=per_instance_results,
            total_snapshots=total_snapshots,
            total_accepted=total_accepted,
            total_rejected=total_rejected,
            overall_outcome=overall_outcome,
            all_snapshots=all_snapshots,
            active_fingerprints=all_fingerprints,
        )

    def _execute_source_instance(
        self,
        instance: SourceInstance,
        run_id: Optional[str],
        dry_run: bool,
        should_fetch_detail,
    ) -> SourceExecutionResult:
        """Execute a single source instance with error isolation."""
        started_at = datetime.now()

        # Check if instance is disabled
        if not instance.enabled:
            return SourceExecutionResult(
                source_instance_id=instance.instance_id,
                source_family=instance.source_family,
                run_id=run_id,
                status="SKIPPED_DISABLED",
                snapshot_count=0,
                accepted_count=0,
                rejected_count=0,
                duration=(datetime.now() - started_at).total_seconds(),
                snapshots=[],
                active_fingerprints=[],
                dry_run=dry_run,
                started_at=started_at,
                completed_at=datetime.now(),
            )

        # Check if instance configuration is valid
        if instance.validation_state != "valid":
            return SourceExecutionResult(
                source_instance_id=instance.instance_id,
                source_family=instance.source_family,
                run_id=run_id,
                status="SKIPPED_INVALID_CONFIGURATION",
                snapshot_count=0,
                accepted_count=0,
                rejected_count=0,
                duration=(datetime.now() - started_at).total_seconds(),
                snapshots=[],
                active_fingerprints=[],
                error_message=f"Invalid configuration state: {instance.validation_state}",
                dry_run=dry_run,
                started_at=started_at,
                completed_at=datetime.now(),
            )

        try:
            # Resolve the plugin through the registry
            adapter = self._registry.get(instance.source_family)

            # Execute ingestion with error isolation
            # EXACT ONCE: Single acquisition per source instance
            ingestion_result = self._ingestion_service.ingest_full_inventory(
                source_name=instance.source_family,
                should_fetch_detail=should_fetch_detail,
            )

            snapshot_count = len(ingestion_result.snapshots)
            # For now, all snapshots are accepted at ingestion time
            accepted_count = snapshot_count
            rejected_count = 0

            return SourceExecutionResult(
                source_instance_id=instance.instance_id,
                source_family=instance.source_family,
                run_id=run_id,
                status="SUCCESS" if snapshot_count > 0 else "PARTIAL_SUCCESS",
                snapshot_count=snapshot_count,
                accepted_count=accepted_count,
                rejected_count=rejected_count,
                duration=(datetime.now() - started_at).total_seconds(),
                snapshots=ingestion_result.snapshots,
                active_fingerprints=ingestion_result.active_fingerprints,
                dry_run=dry_run,
                started_at=started_at,
                completed_at=datetime.now(),
            )

        except SourceError as e:
            return SourceExecutionResult(
                source_instance_id=instance.instance_id,
                source_family=instance.source_family,
                run_id=run_id,
                status="FAILED",
                snapshot_count=0,
                accepted_count=0,
                rejected_count=0,
                duration=(datetime.now() - started_at).total_seconds(),
                snapshots=[],
                active_fingerprints=[],
                error_category="SourceError",
                error_message=str(e),
                dry_run=dry_run,
                started_at=started_at,
                completed_at=datetime.now(),
            )
        except Exception as e:
            return SourceExecutionResult(
                source_instance_id=instance.instance_id,
                source_family=instance.source_family,
                run_id=run_id,
                status="FAILED",
                snapshot_count=0,
                accepted_count=0,
                rejected_count=0,
                duration=(datetime.now() - started_at).total_seconds(),
                snapshots=[],
                active_fingerprints=[],
                error_category="UnexpectedError",
                error_message=str(e),
                dry_run=dry_run,
                started_at=started_at,
                completed_at=datetime.now(),
            )

