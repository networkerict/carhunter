# ARCH-004 - Pipeline and Orchestration

**Document ID:** ARCH-004  
**Project:** CarHunter v3  
**Status:** Draft 1.0  
**Scope Type:** Architecture Definition  
**Depends on:** [docs/ARCHITECTURE.md](../ARCHITECTURE.md), [ARCH-002-Source-Framework.md](./ARCH-002-Source-Framework.md), [ARCH-003-Canonical-Car-Domain-Model.md](./ARCH-003-Canonical-Car-Domain-Model.md)  
**Defers to:** ARCH-005 - Plugin Framework

## Table of Contents

- [1. Executive Summary](#1-executive-summary)
- [2. Purpose](#2-purpose)
- [3. Scope](#3-scope)
- [4. Architectural Context](#4-architectural-context)
- [5. Boundaries with ARCH-002 / ARCH-003 / ARCH-005](#5-boundaries-with-arch-002--arch-003--arch-005)
- [6. Current-State Runtime Baseline](#6-current-state-runtime-baseline)
- [7. Pipeline Modes](#7-pipeline-modes)
- [8. Orchestration Model](#8-orchestration-model)
- [9. Run Lifecycle](#9-run-lifecycle)
- [10. Stage Definitions](#10-stage-definitions)
- [11. Stage Dependency Ordering](#11-stage-dependency-ordering)
- [12. Source-Ingestion Handoff](#12-source-ingestion-handoff)
- [13. Canonical Mapping Runtime Boundary](#13-canonical-mapping-runtime-boundary)
- [14. Compatibility Projection (`cars`)](#14-compatibility-projection-cars)
- [15. Enrichment Flows](#15-enrichment-flows)
- [16. Options Processing](#16-options-processing)
- [17. Scoring and Rescoring](#17-scoring-and-rescoring)
- [18. Recommendation and Notification Flows](#18-recommendation-and-notification-flows)
- [19. Repair / Recheck / Data-Quality Flows](#19-repair--recheck--data-quality-flows)
- [20. Persistence Boundaries](#20-persistence-boundaries)
- [21. Error Handling and Retry Behavior](#21-error-handling-and-retry-behavior)
- [22. Idempotency and Re-run Semantics](#22-idempotency-and-re-run-semantics)
- [23. Scheduling and Triggering Boundary](#23-scheduling-and-triggering-boundary)
- [24. CLI / Web / Operational Entry Points](#24-cli--web--operational-entry-points)
- [25. Observability and Telemetry](#25-observability-and-telemetry)
- [26. Current Architectural Problems](#26-current-architectural-problems)
- [27. Migration Principles](#27-migration-principles)
- [28. Non-Goals](#28-non-goals)
- [29. Open Questions](#29-open-questions)
- [30. Future Evolution](#30-future-evolution)
- [31. Conclusion](#31-conclusion)

## 1. Executive Summary

ARCH-004 defines how CarHunter executes runtime data-processing flows after work is triggered by CLI, web, or scheduler entrypoints.

This document focuses on:

- pipeline modes
- orchestration responsibilities
- stage ordering and dependencies
- run lifecycle and telemetry
- compatibility-preserving processing while the current `cars` table remains active
- the runtime relationship between ARCH-002 source ingestion and ARCH-003 canonical-domain semantics

ARCH-004 does **not** redefine source adapter contracts or canonical domain ownership. Those remain the responsibility of [ARCH-002-Source-Framework.md](./ARCH-002-Source-Framework.md) and [ARCH-003-Canonical-Car-Domain-Model.md](./ARCH-003-Canonical-Car-Domain-Model.md).

## 2. Purpose

### 2.1 ARCHITECTURAL DECISION

The purpose of ARCH-004 is to define the **runtime execution contract** for CarHunter:

- how a run starts
- which stages execute
- in what order they execute
- which stages may mutate compatibility state
- how success, failure, and partial degradation are handled
- how maintenance flows relate to the main pipeline

### 2.2 CURRENT FACT

The current implementation already routes mutable processing through [orchestration.run_pipeline](../../orchestration.py#L128), with stage selection driven by named modes in [orchestration.py](../../orchestration.py#L64).

## 3. Scope

### 3.1 In Scope

- pipeline modes and stage sets
- orchestration context and run coordination
- dependency ordering between ingestion, enrichment, scoring, notification, and cleanup stages
- run tracking and summary reporting
- compatibility-first runtime behavior around the current [cars table](../../database.py#L548)
- maintenance flows such as repair, recheck, and data quality
- scheduler / trigger boundary

### 3.2 Out of Scope

- source adapter interfaces and registry design
- source capability semantics
- canonical Vehicle / Listing / Observation ownership
- final database redesign
- generic plugin loading infrastructure
- deployment automation details beyond the trigger boundary

## 4. Architectural Context

### 4.1 CURRENT FACT

The top-level architecture baseline describes CarHunter as evolving toward deterministic orchestration with compatibility-first persistence in [docs/ARCHITECTURE.md](../ARCHITECTURE.md).

### 4.2 ARCHITECTURAL DECISION

ARCH-004 applies after a runtime trigger and coordinates the processing path that spans:

```text
trigger
    -> orchestration
    -> source ingestion
    -> canonical mapping boundary
    -> compatibility projection and downstream processing
```

### 4.3 FUTURE DESIGN

The intended long-term runtime shape is:

```text
Trigger
    -> Orchestration
    -> ARCH-002 SourceIngestionService
    -> SourceSnapshot
    -> ARCH-003 canonical mapping
    -> Canonical Domain Model
    -> compatibility projection / derived processing
    -> notifications / reports
```

### 4.4 CURRENT LIMITATION

The current implementation does not yet have explicit `SourceSnapshot` or canonical-domain runtime objects. It still moves directly from source-specific scraping to `cars`-compatible payloads in [normalize_car](../../scraper.py#L661) and [save_car](../../database.py#L265).

## 5. Boundaries with ARCH-002 / ARCH-003 / ARCH-005

### 5.1 ARCHITECTURAL DECISION

ARCH-002 owns:

- source adapter behavior
- source request policy
- source capabilities
- `SourceSnapshot`

### 5.2 ARCHITECTURAL DECISION

ARCH-003 owns:

- canonical mapping semantics after `SourceSnapshot`
- Vehicle / Listing / Observation / Provenance / Enrichment ownership
- compatibility semantics of the `cars` projection relative to the canonical model

### 5.3 ARCHITECTURAL DECISION

ARCH-004 owns:

- execution modes
- stage orchestration
- ordering and dependency rules
- run tracking
- failure policy
- idempotency classification
- operational maintenance flow placement

### 5.4 ARCHITECTURAL DECISION

ARCH-005, if defined later, should own only generic plugin infrastructure. It must not redefine:

- stage ordering
- run lifecycle semantics
- source-to-domain boundaries
- compatibility projection policy

## 6. Current-State Runtime Baseline

### 6.1 CURRENT FACT

The current mutable runtime path is centralized in [orchestration.py](../../orchestration.py).

Key implemented pieces:

- run coordination: [run_pipeline](../../orchestration.py#L128)
- stage registry: [register_stage](../../orchestration.py#L51)
- pipeline context: [PipelineContext](../../orchestration.py#L38)
- full-run tracking: [pipeline.start_run](../../pipeline.py#L10), [pipeline.finish_run](../../pipeline.py#L38)

### 6.2 CURRENT FACT

Current full-mode stage order is:

```text
scrape
    -> descriptions
    -> options
    -> scores
    -> deal_scores
    -> notifications
    -> statistics
    -> summary_notifications
    -> cleanup
```

Evidence:

- [PIPELINE_MODES.full](../../orchestration.py#L64)
- [docs/Pipeline.md](../../docs/Pipeline.md)
- [test_full_mode_uses_canonical_stage_order_and_tracking](../../tests/test_orchestration.py#L46)

### 6.3 CURRENT LIMITATION

The current documentation summary in [Pipeline.md](../../docs/Pipeline.md#L7) omits the implemented `summary_notifications` stage from the `full` mode stage list.

## 7. Pipeline Modes

### 7.1 CURRENT FACT

Current implemented modes are:

- `full`
- `rescore`
- `options`
- `descriptions`
- `repair`
- `recheck`

Evidence:

- [orchestration.py](../../orchestration.py#L64)
- [autohunter.py](../../autohunter.py#L290)

### 7.2 ARCHITECTURAL DECISION

Pipeline modes are **named orchestration contracts**, not just CLI shortcuts.

Each mode must define:

- included stages
- run-tracking behavior
- whether writes are expected
- whether notifications are allowed
- whether the mode is operational, diagnostic, or maintenance-oriented

### 7.3 ARCHITECTURAL DECISION

v3.0 mode classification is:

- `full`: mutable full pipeline run; may be scheduler-triggered or manually triggered
- `rescore`: mutable maintenance run that refreshes options and recalculates derived scores
- `options`: mutable maintenance run for option-analysis refresh only
- `descriptions`: mutable maintenance run for description enrichment only
- `repair`: mutable maintenance run for targeted source re-fetch and compatibility repair
- `recheck`: mutating diagnostic/maintenance run used for inspection plus selective refresh of details and missing options

### 7.4 ARCHITECTURAL DECISION

The scheduled daily pipeline in v3.0 is the `full` mode only. Maintenance and diagnostic modes are not part of the automatic scheduled full run unless a future architecture revision explicitly changes that contract.

### 7.5 ARCHITECTURAL DECISION

Manual full runs execute the same stage contract as scheduled full runs. Trigger origin may differ, but stage ordering, mutation scope, run identity, failure handling, and concurrency rules remain the same.

### 7.6 ARCHITECTURAL DECISION

No read-only orchestration mode is currently defined in `orchestration.py`. Read-only diagnostics, reporting, and UI queries remain outside mutable orchestration unless a future mode is explicitly introduced as read-only.

### 7.7 CURRENT FACT

Only the `full` mode currently enables run tracking and summary printing through [ModeDefinition.track_pipeline_run](../../orchestration.py#L33) and [ModeDefinition.print_summary](../../orchestration.py#L34).

## 8. Orchestration Model

### 8.1 CURRENT FACT

The current orchestration model is stage-list execution over a mutable [PipelineContext](../../orchestration.py#L38).

`PipelineContext` currently carries:

- `mode`
- `dry_run`
- `started_at`
- `run_id`
- `stage_results`
- `stats`
- `alerts_sent`

### 8.2 ARCHITECTURAL DECISION

Orchestration is the runtime coordination layer. It should:

- accept a trigger and selected mode
- execute stages in a deterministic order
- collect run-level outcomes
- apply run-level failure handling
- remain separate from source-specific parsing and domain ownership definitions

### 8.3 ARCHITECTURAL DECISION

For v3.0, orchestration owns:

- mode selection after a trigger reaches the runtime
- run-level lock acquisition for mutable runs
- stage ordering
- stage dispatch
- run identity
- run outcome classification
- coordination of compatibility writes, operational telemetry, and notification side effects

The triggering mechanism may request a run, but it does not own orchestration state after handoff.

### 8.4 CURRENT LIMITATION

The current context model does not provide explicit:

- stage input/output contracts
- stage checkpoints
- per-stage status tracking
- concurrency guards

## 9. Run Lifecycle

### 9.1 CURRENT FACT

Tracked full runs currently follow this lifecycle:

```text
RUNNING
    -> SUCCESS
    or
    -> FAILED
```

Evidence:

- [pipeline.start_run](../../pipeline.py#L10)
- [pipeline.finish_run](../../pipeline.py#L38)

### 9.2 CURRENT FACT

Persisted run fields currently include:

- `started_at`
- `finished_at`
- `status`
- aggregate counters such as `new_cars`, `options_updated`, `alerts_sent`
- `error_message`

See [pipeline_runs](../../database.py#L641).

### 9.3 CURRENT LIMITATION

There is no persisted stage-level lifecycle in the current implementation, even though [docs/ARCHITECTURE.md](../ARCHITECTURE.md#L451) names future `stage_runs`.

### 9.4 ARCHITECTURAL DECISION

v3.0 run lifecycle semantics apply to:

- full scheduled runs
- manual maintenance runs
- targeted reprocessing runs
- diagnostic runs

without requiring immediate `stage_runs` implementation in v3.0.

### 9.5 ARCHITECTURAL DECISION

Every mutable orchestration execution is a distinct run intent. A full pipeline rerun starts a new run and must not silently reuse the identity of a prior failed or completed run.

### 9.6 CURRENT LIMITATION

The current implementation persists aggregate run identity only for `full` mode. Other modes execute as orchestration runs conceptually, but do not yet share the same durable run ledger.

## 10. Stage Definitions

### 10.1 CURRENT FACT

Current stages are registered in [orchestration.py](../../orchestration.py) and implemented as stage functions:

- `scrape`
- `descriptions`
- `options`
- `scores`
- `deal_scores`
- `notifications`
- `statistics`
- `summary_notifications`
- `cleanup`
- `repair`
- `recheck`

### 10.2 ARCHITECTURAL DECISION

ARCH-004 classifies stages into four categories:

1. **Core ingestion and processing stages**
2. **Derived-state stages**
3. **Notification/reporting stages**
4. **Maintenance/diagnostic stages**

### 10.3 ARCHITECTURAL DECISION

Each stage contract in v3.0 is defined by:

- trigger mode(s)
- required upstream state
- allowed writes
- allowed external side effects
- failure classification
- retry / rerun / resume classification
- emitted run telemetry

### 10.4 CURRENT LIMITATION

Current stages are implemented as Python functions without explicit declared contracts for:

- required inputs
- produced outputs
- hard-fail / soft-fail policy
- idempotency class

## 11. Stage Dependency Ordering

### 11.1 CURRENT FACT

Current dependencies are implicit in ordered stage lists in [PIPELINE_MODES](../../orchestration.py#L64).

### 11.2 ARCHITECTURAL DECISION

The v3.0 dependency order for the scheduled full run is:

1. ingestion before enrichment
2. enrichment before options if enrichment may affect option-detection inputs
3. options before scores
4. scores before deal scoring
5. scores and deal scoring before notifications
6. statistics after scoring outcomes are finalized for the run
7. cleanup last

### 11.3 ARCHITECTURAL DECISION

The v3.0 scheduled full-run stage order is:

```text
scrape
    -> descriptions
    -> options
    -> scores
    -> deal_scores
    -> notifications
    -> statistics
    -> summary_notifications
    -> cleanup
```

### 11.4 CURRENT LIMITATION

There is no explicit dependency model beyond list order. If a stage is inserted incorrectly, current code has no structural guard beyond tests such as [test_full_mode_uses_canonical_stage_order_and_tracking](../../tests/test_orchestration.py#L46).

## 12. Source-Ingestion Handoff

### 12.1 ARCHITECTURAL DECISION

ARCH-004 begins at the point where orchestration invokes source ingestion, but it does not redefine source adapter behavior.

### 12.2 FUTURE DESIGN

The runtime handoff expected by the architecture is:

```text
orchestration
    -> ARCH-002 SourceIngestionService
    -> SourceSnapshot
```

### 12.3 CURRENT FACT

Today orchestration calls the AutoScout24-specific scraper directly in [stage_scrape](../../orchestration.py#L220), which invokes [scraper.run_scraper](../../scraper.py#L803).

### 12.4 CURRENT LIMITATION

Current runtime code bypasses the future `SourceIngestionService` concept defined by ARCH-002 and therefore does not yet expose an explicit source-ingestion contract to orchestration.

## 13. Canonical Mapping Runtime Boundary

### 13.1 ARCHITECTURAL DECISION

ARCH-004 must treat canonical mapping as a distinct runtime boundary after `SourceSnapshot` and before compatibility projection or downstream derived processing.

### 13.2 CURRENT FACT

ARCH-003 defines canonical mapping ownership after `SourceSnapshot` in [ARCH-003-Canonical-Car-Domain-Model.md](./ARCH-003-Canonical-Car-Domain-Model.md).

### 13.3 CURRENT LIMITATION

The current implementation has no explicit canonical mapping stage. Instead, [normalize_car](../../scraper.py#L661) constructs a `cars`-shaped payload directly from source-shaped input.

### 13.4 FUTURE DESIGN

Future runtime shape should make the boundary explicit:

```text
SourceSnapshot
    -> canonical mapping
    -> canonical domain state
    -> compatibility projection
```

## 14. Compatibility Projection (`cars`)

### 14.1 CURRENT FACT

The current `cars` table remains the active compatibility projection for:

- search and ranking queries in [database.py](../../database.py#L786)
- score persistence in [database.py](../../database.py#L222)
- sold detection in [database.py](../../database.py#L1163)
- deal queries in [database.py](../../database.py#L1089)
- watchlist alerts in [database.py](../../database.py#L1119)

### 14.2 ARCHITECTURAL DECISION

ARCH-004 must preserve compatibility-first runtime behavior while the system still depends on the current `cars` projection.

### 14.3 MIGRATION PRINCIPLE

In v3.0 compatibility mode, orchestration may continue to write and derive state through `cars`, but ARCH-004 must make clear that this is a compatibility runtime path rather than the final target architecture.

### 14.4 CURRENT LIMITATION

The current row wrapper [Car](../../models.py#L7) is tightly coupled to positional schema layout and demonstrates that runtime pipeline behavior still depends on the compatibility projection directly.

## 15. Enrichment Flows

### 15.1 CURRENT FACT

Current enrichment-like flows include:

- description backfill in [descriptions.py](../../descriptions.py#L13)
- repair in [repair_engine.py](../../repair_engine.py#L346)
- historical backfill in [data_quality.py](../../data_quality.py#L181)

### 15.2 CURRENT LIMITATION

These flows are not unified behind one enrichment contract. They fetch source data directly and mutate `cars` directly.

### 15.3 ARCHITECTURAL DECISION

Enrichment stages operate **after ingestion** and **before or alongside derived-state recalculation**, while respecting ARCH-003 ownership boundaries for source data, canonical facts, and enrichment outputs.

## 16. Options Processing

### 16.1 CURRENT FACT

Options processing currently consists of:

- [update_all_options](../../options.py#L320)
- [update_car_options](../../options.py#L353)
- persistence through [database.update_car_options](../../database.py#L138)

`rescore` forces an options refresh via [orchestration.py](../../orchestration.py#L81).

### 16.2 CURRENT LIMITATION

Options are stored as text in `options_found` and score in `options_score`, both directly on the compatibility row.

### 16.3 CURRENT LIMITATION

The current scrape persistence path can overwrite `options_found` through [save_car](../../database.py#L335) even though [normalize_car](../../scraper.py#L680) does not compute options-derived text. This creates a runtime coupling hazard between ingestion and later enrichment stages.

### 16.4 ARCHITECTURAL DECISION

Ingestion must not be treated as authoritative for enrichment-derived compatibility fields unless the ingestion payload explicitly owns those fields by architecture. Where compatibility writes can overwrite downstream derived fields, the affected derived stage must be rerun before the run is considered complete.

## 17. Scoring and Rescoring

### 17.1 CURRENT FACT

Scoring is recalculated in [scoring.recalculate_scores](../../scoring.py#L198), which:

- loads cars from [database.get_all_cars](../../database.py#L1041)
- computes base scores in [calculate_final_score](../../scoring.py#L272)
- computes watchlist and personal score through matcher logic
- writes results through [update_car_scores](../../database.py#L222)

### 17.2 CURRENT FACT

Deal scoring runs afterward through [deals.update_deal_scores](../../deals.py#L11) using [deal_score.calculate_deal_score](../../deal_score.py#L7).

### 17.3 CURRENT LIMITATION

Current scoring operates directly on compatibility rows rather than canonical domain objects or observation histories.

### 17.4 ARCHITECTURAL DECISION

Scoring, personal scoring, watchlist matching, and deal scoring are downstream derived-state stages whose ordering is explicit and whose persistence remains compatibility-bound until future evolution separates them.

## 18. Recommendation and Notification Flows

### 18.1 CURRENT FACT

Recommendation logic exists in:

- [recommendation_engine.py](../../recommendation_engine.py#L14)
- [recommendation.py](../../recommendation.py#L7)

Current orchestration does not run recommendation generation as a named pipeline stage.

### 18.2 CURRENT FACT

Current pipeline notifications are sent in:

- [stage_notifications](../../orchestration.py#L310)
- [stage_summary_notifications](../../orchestration.py#L380)

These stages query scored/deal-filtered rows and use Telegram senders.

### 18.3 CURRENT LIMITATION

Recommendation and notification are not fully separated in runtime architecture today. Notification eligibility is based on persisted compatibility fields and query rules, not an explicit recommendation-stage output.

### 18.4 ARCHITECTURAL DECISION

ARCH-004 distinguishes:

- derived recommendation computation
- alert eligibility determination
- external notification side effects

### 18.5 ARCHITECTURAL DECISION

Recommendation is **not** a mandatory core stage of the scheduled full pipeline in v3.0. It remains a derived/application concern that may consume scored compatibility state or be produced by reporting/application flows outside the scheduled full-run stage chain.

### 18.6 ARCHITECTURAL DECISION

Notification is an orchestration side effect that may consume available scored compatibility state and any recommendation-like output that is already available, but it must not require a persisted Recommendation artifact in v3.0.

### 18.7 FUTURE DESIGN

A future Recommendation artifact may become a dedicated runtime output without changing the canonical Vehicle model defined by ARCH-003.

## 19. Repair / Recheck / Data-Quality Flows

### 19.1 CURRENT FACT

Maintenance and diagnostic flows currently include:

- repair mode in [stage_repair](../../orchestration.py#L448)
- recheck mode in [stage_recheck](../../orchestration.py#L467)
- historical backfill in [BackfillEngine.run_backfill](../../data_quality.py#L181)
- integrity and dashboard quality reporting in [data_quality.py](../../data_quality.py)

### 19.2 CURRENT FACT

Repair persists run reports to `repair_runs` in [repair_engine.py](../../repair_engine.py#L314). Backfill reports are persisted to `backfill_runs` in [data_quality.py](../../data_quality.py#L433).

### 19.3 CURRENT LIMITATION

These maintenance flows are not part of a unified run-tracking model and are not represented in `pipeline_runs`.

### 19.4 ARCHITECTURAL DECISION

Maintenance and diagnostic flows are first-class orchestration concerns, but they remain separate from the scheduled full run in v3.0.

## 20. Persistence Boundaries

### 20.1 CURRENT FACT

Persistence today is coordinated through [database.py](../../database.py), with tables including:

- `cars`
- `pipeline_runs`
- `repair_runs`
- `backfill_runs`

### 20.2 CURRENT LIMITATION

Multiple stages and maintenance modules write directly to persistence without a separate orchestration-owned persistence abstraction.

### 20.3 ARCHITECTURAL DECISION

ARCH-004 defines **persistence coordination boundaries**, not a new storage layer. In v3.0:

- which stages are allowed to write compatibility state
- which stages are read-only
- which stages create operational telemetry
- which stages may emit external side effects

### 20.4 ARCHITECTURAL DECISION

Stage write authority in v3.0 is:

- `scrape`: may write compatibility ingestion state and sold-state reconciliation inputs
- `descriptions`: may write description enrichment fields
- `options`: may write options enrichment and option score fields
- `scores`: may write score, personal-score, and watchlist-match fields
- `deal_scores`: may write deal-score fields
- `notifications` / `summary_notifications`: may write notification delivery state only where delivery tracking is required
- `statistics`: read-only over compatibility state; may emit telemetry summaries
- `cleanup`: may mutate operational telemetry tables only
- `repair` / `recheck` / backfill flows: may write compatibility repair or maintenance fields as defined by their mode contracts

## 21. Error Handling and Retry Behavior

### 21.1 CURRENT FACT

Current behavior differs by module:

- scrape HTTP fetches return empty text on request failure in [http_get](../../scraper.py#L72)
- scrape/detail parsing often soft-fails to empty or `None` in [scraper.py](../../scraper.py)
- orchestration marks tracked full runs failed on uncaught exceptions in [run_pipeline](../../orchestration.py#L178)
- notification stages catch exceptions and continue in [stage_notifications](../../orchestration.py#L358) and [stage_summary_notifications](../../orchestration.py#L422)
- repair continues after per-car failure in [repair_engine.py](../../repair_engine.py#L261)

### 21.2 CURRENT LIMITATION

There is no explicit architecture-level policy for:

- hard-fail stages
- soft-fail stages
- retryable failures
- degraded-success outcomes

### 21.3 ARCHITECTURAL DECISION

Failure semantics in v3.0 are defined per stage category:

- ingestion
- processing/enrichment
- derived-state recalculation
- notifications
- maintenance

without requiring immediate implementation of centralized retry orchestration.

### 21.4 ARCHITECTURAL DECISION

The v3.0 baseline failure model is:

- **ingestion failure:** may fail the mutable full run if required inventory acquisition cannot complete
- **processing/enrichment failure:** may fail the active run unless explicitly classified as best-effort maintenance enrichment
- **derived-state failure:** fails the active mutable run because downstream ranking and notification decisions depend on consistent derived outputs
- **notification failure:** does not rewrite completed data-processing stages; notification failure is isolated from already-persisted compatibility state
- **maintenance per-record failure:** may continue at record scope where the mode explicitly supports partial continuation, as in current repair behavior

### 21.5 CURRENT LIMITATION

The current implementation does not yet persist a distinct degraded-success state, resumable checkpoints, or per-stage failure records.

## 22. Idempotency and Re-run Semantics

### 22.1 CURRENT FACT

Current stages have mixed idempotency characteristics:

- score recalculation is mostly overwrite-idempotent
- deal score recalculation is mostly overwrite-idempotent
- sold detection is stateful and depends on the current active fingerprint set
- notifications are side-effecting
- repair and backfill are conditional mutation flows

### 22.2 CURRENT FACT

Sold-detection behavior and reappearance handling are covered by tests in [tests/test_sold_detection.py](../../tests/test_sold_detection.py).

### 22.3 ARCHITECTURAL DECISION

ARCH-004 classifies stages by re-run semantics:

- deterministic overwrite
- state transition
- history-producing
- side-effecting external notification
- maintenance repair

### 22.4 ARCHITECTURAL DECISION

Retry and recovery scopes are distinct:

1. **Source / external retry**  
   Owned by ARCH-002. This covers HTTP/API retry, transient source unavailability, and throttling behavior.
2. **Stage retry**  
   Owned by ARCH-004. This re-executes one orchestration stage within the same run boundary without replaying unrelated completed stages.
3. **Full pipeline rerun**  
   Owned by ARCH-004. This starts a new run identity and re-executes the selected mode from its defined first stage.
4. **Resume**  
   Owned by ARCH-004. This continues an incomplete run from a durable checkpoint and is valid only for stages explicitly classified as resumable.
5. **Side effects**  
   Compatibility writes, sold-state transitions, and notifications must never be blindly replayed without the idempotency guarantees defined for their stage class.

### 22.5 ARCHITECTURAL DECISION

Until durable checkpoints exist, failed mutable runs in v3.0 are rerun as new runs rather than resumed in place.

### 22.6 ARCHITECTURAL DECISION

The v3.0 stage-class matrix is:

| Stage / class | Retryable? | Rerunnable? | Resumable? | Idempotency requirement | Automatic retry allowed? |
|---|---|---|---|---|---|
| Source discovery / fetch | Via ARCH-002 only | Yes, through a new run or restarted stage contract | No current durable checkpoint | safe repeat of source reads only | Defined by ARCH-002, not ARCH-004 |
| Canonical mapping | Not currently implemented as explicit stage | Yes | No current durable checkpoint | deterministic mapping for same input snapshot | No current automatic retry |
| Compatibility persistence / `save_car` writes | Not blindly | Yes, but only as defined compatibility overwrite logic | No | must preserve compatibility invariants and avoid duplicate-row corruption | No |
| Sold detection / listing-activity reconciliation | Not blindly | Yes, only as a full stage with the correct active set | No | must be state-transition-safe for the active run's inventory set | No |
| Description enrichment | Yes | Yes | No current durable checkpoint | repeated execution must not degrade existing richer values | No current automatic retry |
| Options enrichment | Yes | Yes | No current durable checkpoint | repeated execution must converge on the same options/score result for the same inputs | No current automatic retry |
| Scoring | Yes | Yes | No current durable checkpoint | overwrite-idempotent for the same compatibility state | No current automatic retry |
| Deal scoring | Yes | Yes | No current durable checkpoint | overwrite-idempotent for the same compatibility state | No current automatic retry |
| Statistics / reporting | Yes | Yes | No current durable checkpoint needed | read-only reproducibility over current persisted state | No current automatic retry |
| Notifications | Not blindly | Limited rerun only with delivery-idempotency rules | No | must not duplicate externally visible alerts | No |
| Maintenance / repair | Per-record only where mode supports it | Yes, as a new maintenance run | No current durable checkpoint | must preserve better existing values and avoid destructive downgrade | No current automatic retry |
| Data-quality backfill | Per-record only | Yes, as a new maintenance run | Limited only when a durable backfill state exists for that subsystem | must fill missing fields without overwriting better existing values | No current automatic retry |

### 22.7 CURRENT LIMITATION

The current codebase does not persist explicit per-stage idempotency metadata or re-run markers.

## 23. Scheduling and Triggering Boundary

### 23.1 CURRENT FACT

The current scheduling model is operationally documented as systemd timer/service based:

- [docs/Operations.md](../../docs/Operations.md)
- [docs/Deployment.md](../../docs/Deployment.md)
- [docs/ARCHITECTURE.md](../ARCHITECTURE.md#L385)

### 23.2 CURRENT LIMITATION

The repository snapshot does not contain the actual service and timer unit files.

### 23.3 ARCHITECTURAL DECISION

ARCH-004 defines the **boundary** between triggers and orchestration, not the full deployment mechanism. It distinguishes:

- scheduled runs
- manual CLI runs
- web-triggered runs
- maintenance runs

### 23.4 ARCHITECTURAL DECISION

The scheduler or trigger starts a run request. Orchestration owns mutable run state after that handoff.

### 23.5 ARCHITECTURAL DECISION

In v3.0, only one mutable full run may be active at a time.

### 23.6 ARCHITECTURAL DECISION

Orchestration owns the run-level lock for mutable full runs. The triggering mechanism does not own orchestration state, lock state, or run progression.

### 23.7 ARCHITECTURAL DECISION

Lock behavior for v3.0 is:

- lock acquisition occurs before the first mutable stage of a mutable full run
- the active orchestration run owns the lock until normal completion or failure handling completes
- lock release occurs when the mutable full run finishes or fails terminally
- if lock acquisition fails, the second mutable full run is rejected or not started
- after abnormal termination, lock recovery must require explicit orchestration-side stale-lock handling or operator intervention; the scheduler alone must not assume a run completed successfully

### 23.8 ARCHITECTURAL DECISION

Mutating maintenance modes must not run concurrently with a mutable full run.

### 23.9 ARCHITECTURAL DECISION

Read-only diagnostic operations may run concurrently only when they do not mutate compatibility state, operational telemetry, or notification state.

### 23.10 CURRENT LIMITATION

The current implementation does not yet expose an explicit orchestration lock, stale-lock recovery mechanism, or durable checkpoint-based resume support.

## 24. CLI / Web / Operational Entry Points

### 24.1 CURRENT FACT

CLI entrypoints in [autohunter.py](../../autohunter.py) route to orchestration for mutable processing modes such as:

- `options`
- `descriptions`
- `rescore`
- `full`
- `repair`
- `recheck`

### 24.2 CURRENT FACT

The web app delegates rescore to orchestration in [webapp.py](../../webapp.py#L275).

### 24.3 ARCHITECTURAL DECISION

Entry points should select run intent and parameters, but orchestration should remain the owner of:

- stage order
- run semantics
- processing coordination

## 25. Observability and Telemetry

### 25.1 CURRENT FACT

Current run telemetry is available through:

- `pipeline_runs` persistence in [database.py](../../database.py#L641)
- reporting in [pipeline_report.py](../../pipeline_report.py)
- aggregate dashboard helpers in [pipeline_stats.py](../../pipeline_stats.py)

### 25.2 CURRENT FACT

Current quality and maintenance telemetry is split across:

- `repair_runs`
- `backfill_runs`
- dashboard and integrity helpers in [data_quality.py](../../data_quality.py)

### 25.3 CURRENT LIMITATION

There is no stage-level telemetry table, structured stage checkpoint log, or unified telemetry model across full, maintenance, and diagnostic runs.

### 25.4 FUTURE DESIGN

Future telemetry may expand to:

- stage-level checkpoints
- unified maintenance-run lineage
- structured correlation fields such as run_id, stage_id, source_name, and compatibility entity identifiers

## 26. Current Architectural Problems

### 26.1 CURRENT LIMITATION

The current implementation does not yet expose the intended `SourceSnapshot -> canonical mapping -> canonical domain` runtime path. Instead it still follows a compatibility-direct scrape flow through [normalize_car](../../scraper.py#L661) and [save_car](../../database.py#L265).

### 26.2 CURRENT LIMITATION

Source refresh, enrichment, and derived-state updates all mutate the same `cars` row, which creates cross-stage coupling and overwrite risk.

### 26.3 CURRENT LIMITATION

Run telemetry is fragmented:

- full runs use `pipeline_runs`
- repair uses `repair_runs`
- backfill uses `backfill_runs`

### 26.4 CURRENT LIMITATION

Failure policy is inconsistent across stages and maintenance flows.

### 26.5 CURRENT LIMITATION

Some runtime fields affect downstream logic without a clearly defined architectural owner, for example `cars.status` in [deal_score.py](../../deal_score.py#L36).

## 27. Migration Principles

### 27.1 MIGRATION PRINCIPLE

Preserve the current `cars`-based operational system while clarifying orchestration semantics.

### 27.2 MIGRATION PRINCIPLE

Make runtime boundaries explicit before replacing compatibility-direct flows.

### 27.3 MIGRATION PRINCIPLE

Keep scheduled and manual production behavior stable while introducing clearer stage contracts and telemetry.

### 27.4 MIGRATION PRINCIPLE

Separate runtime concerns before introducing new infrastructure:

- source ingestion boundary
- canonical mapping boundary
- compatibility projection boundary
- enrichment boundary
- derived-state boundary
- notification side-effect boundary

## 28. Non-Goals

ARCH-004 does not define:

- source adapter method signatures
- canonical Vehicle or Listing schemas
- final database normalization
- recommendation scoring formulas
- plugin loader implementation
- deployment scripts or service-unit contents

## 29. Open Questions

### 29.1 OPEN QUESTION

Should v3 compatibility mode continue to allow direct source-to-`cars` persistence, or should a compatibility mapper abstraction become mandatory before further pipeline evolution?

### 29.2 OPEN QUESTION

Should maintenance flows such as repair and backfill remain separate operational subsystems, or become standardized orchestration modes with unified telemetry?

### 29.3 OPEN QUESTION

Should notification stages always soft-fail, or should some operational alert failures affect overall run status?

### 29.4 OPEN QUESTION

When the Source Framework becomes multi-source, what stage owns sold-detection and listing-activity reconciliation semantics?

## 30. Future Evolution

### 30.1 FUTURE DESIGN

Future runtime evolution may include:

- explicit source ingestion services
- explicit canonical mapping stages
- stage-level telemetry
- clearer notification/recommendation separation
- richer rerun and recovery semantics
- unified maintenance-run orchestration

### 30.2 FUTURE DESIGN

Those changes must preserve the source boundary from ARCH-002 and the domain ownership boundary from ARCH-003.

## 31. Conclusion

### 31.1 ARCHITECTURAL DECISION

ARCH-004 defines CarHunter’s runtime execution model after a trigger enters the system.

### 31.2 ARCHITECTURAL DECISION

It formalizes the current stage-based orchestration pattern around [orchestration.run_pipeline](../../orchestration.py#L128) while clearly distinguishing implemented behavior from target architecture.

### 31.3 MIGRATION PRINCIPLE

The document preserves compatibility-first runtime behavior while making room for the future `SourceSnapshot -> canonical mapping -> canonical domain -> compatibility projection` execution path required by ARCH-002 and ARCH-003.
