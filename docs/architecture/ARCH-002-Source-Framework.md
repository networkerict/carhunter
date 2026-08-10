# ARCH-002 – Source Framework

**Document ID:** ARCH-002  
**Project:** CarHunter v3  
**Status:** Draft 1.0  
**Scope Type:** Architecture Definition  
**Depends on:** ARCH-001 – High Level Architecture, [docs/ARCHITECTURE.md](/opt/carhunter/v3.0-dev/docs/ARCHITECTURE.md)  
**Defers to:** ARCH-003 – Canonical Car Model / Domain Model

## Table of Contents

- [1. Executive Summary](#1-executive-summary)
- [2. Purpose and Scope](#2-purpose-and-scope)
- [3. Architectural Boundary](#3-architectural-boundary)
- [4. Current-State Baseline](#4-current-state-baseline)
- [5. Source Abstraction Goals](#5-source-abstraction-goals)
- [6. Source Adapter / Plugin Model](#6-source-adapter--plugin-model)
- [7. Source Interface / Contract](#7-source-interface--contract)
- [8. Source DTO Concepts](#8-source-dto-concepts)
- [9. Listing Discovery](#9-listing-discovery)
- [10. Listing Detail Retrieval](#10-listing-detail-retrieval)
- [11. Source-Specific Normalization Boundary](#11-source-specific-normalization-boundary)
- [12. Source Identity and Source Listing IDs](#12-source-identity-and-source-listing-ids)
- [13. Source Provenance](#13-source-provenance)
- [14. Error Handling and Retry Semantics](#14-error-handling-and-retry-semantics)
- [15. Rate Limiting and Request Policy](#15-rate-limiting-and-request-policy)
- [16. Source Capabilities](#16-source-capabilities)
- [17. Source Configuration](#17-source-configuration)
- [18. Source Lifecycle and Health](#18-source-lifecycle-and-health)
- [19. Pipeline Integration](#19-pipeline-integration)
- [20. Data Ownership Boundaries](#20-data-ownership-boundaries)
- [21. Interaction with ARCH-003](#21-interaction-with-arch-003)
- [22. Relationship with ARCH-005](#22-relationship-with-arch-005)
- [23. Backward Compatibility with the Current `cars` Table](#23-backward-compatibility-with-the-current-cars-table)
- [24. Migration Path from the Current AutoScout24 Scraper](#24-migration-path-from-the-current-autoscout24-scraper)
- [25. Testing Strategy](#25-testing-strategy)
- [26. Security Considerations](#26-security-considerations)
- [27. Observability Requirements](#27-observability-requirements)
- [28. Architectural Constraints](#28-architectural-constraints)
- [29. Explicit Non-Goals](#29-explicit-non-goals)
- [30. Open Questions Deferred to ARCH-003](#30-open-questions-deferred-to-arch-003)
- [31. Summary](#31-summary)

## 1. Executive Summary

CarHunter currently ingests vehicle listings through a single AutoScout24-specific implementation in [scraper.py](/opt/carhunter/v3.0-dev/scraper.py). Discovery, source parsing, source-specific normalization, and compatibility with the current persistence model are tightly coupled in one module.

ARCH-002 defines the **Source Framework** that will separate source-specific concerns from application core behavior while preserving the compatibility-first approach defined in [docs/ARCHITECTURE.md](/opt/carhunter/v3.0-dev/docs/ARCHITECTURE.md).

This document defines:

- the source abstraction boundary
- the source adapter/plugin model
- source-owned data and provenance
- source capabilities and request policy
- pipeline integration
- compatibility with the current `cars` table
- the migration path from the current AutoScout24 scraper

This document does **not** define the canonical Car model in detail. That is the responsibility of ARCH-003.

## 2. Purpose and Scope

### 2.1 Purpose

The purpose of ARCH-002 is to define how CarHunter abstracts vehicle/listing sources from:

- scoring
- recommendation
- watchlist logic
- persistence consumers
- dashboard and reporting logic

### 2.2 In Scope

- source adapter boundaries
- source contracts and DTO concepts
- listing discovery and detail retrieval
- source identity and source listing IDs
- source provenance
- source capabilities
- request, retry, and rate-limit policy
- source lifecycle and health
- pipeline integration
- compatibility bridge to the current `cars` table
- migration from the current AutoScout24 implementation

### 2.3 Out of Scope

- detailed canonical Car/domain modeling
- dealer, pricing-history, enrichment, or recommendation domain schemas
- final persistence redesign
- PostgreSQL migration design
- dashboard/API redesign
- scoring redesign

## 3. Architectural Boundary

ARCH-002 defines the **SOURCE abstraction**.

ARCH-003 defines the **CANONICAL DOMAIN MODEL**.

The Source Framework is responsible for turning source-specific remote data into a stable, source-owned handoff object. It must not embed business scoring, recommendation, or canonical domain semantics.

### 3.1 FUTURE DESIGN

The intended source-to-domain boundary is:

```text
Source Adapter
    -> SourceSnapshot
    -> ARCH-003 canonical mapping
    -> Canonical Car / Domain Model
```

`SourceSnapshot` is the explicit output of ARCH-002. Canonical mapping begins after that handoff and is owned by ARCH-003.

## 4. Current-State Baseline

### 4.1 CURRENT FACT

The current implementation is single-source and AutoScout24-specific.

Primary implementation points:

- scrape stage entrypoint: [stage_scrape](/opt/carhunter/v3.0-dev/orchestration.py:224)
- pipeline scrape runner: [run_scraper](/opt/carhunter/v3.0-dev/scraper.py:803)
- listing discovery: [fetch_page](/opt/carhunter/v3.0-dev/scraper.py:395), [parse_page](/opt/carhunter/v3.0-dev/scraper.py:403)
- detail retrieval: [fetch_car_details](/opt/carhunter/v3.0-dev/scraper.py:238)
- description retrieval: [fetch_description](/opt/carhunter/v3.0-dev/scraper.py:183)
- source URL normalization: [normalize_url](/opt/carhunter/v3.0-dev/scraper.py:46)
- source-specific fingerprint construction: [create_fingerprint](/opt/carhunter/v3.0-dev/scraper.py:429)
- source-specific normalization into current DB payload shape: [normalize_car](/opt/carhunter/v3.0-dev/scraper.py:661)

The current scrape flow is:

```text
orchestration.stage_scrape
    -> scraper.run_scraper
        -> fetch discovery pages
        -> parse listings
        -> fetch details for new listings
        -> normalize into current flat payload
        -> database.save_car
        -> database.mark_missing_cars_sold
```

### 4.2 CURRENT FACT

Source behavior is also reused outside the main scrape stage:

- description updates in [descriptions.py](/opt/carhunter/v3.0-dev/descriptions.py)
- repair in [repair_engine.py](/opt/carhunter/v3.0-dev/repair_engine.py)
- backfill/data quality in [data_quality.py](/opt/carhunter/v3.0-dev/data_quality.py)
- recheck flow in [orchestration.py](/opt/carhunter/v3.0-dev/orchestration.py:471)

### 4.3 CURRENT FACT

The current persistence model is still the `cars` table in [database.py](/opt/carhunter/v3.0-dev/database.py:548), with continuity driven by:

- `autoscout_id`
- `fingerprint`
- `url`
- `first_seen`
- `last_seen`
- `last_price`
- `price_drop`
- `sold`
- `sold_at`

### 4.4 Problem Statement

The current approach couples:

- remote source protocol
- marketplace payload parsing
- source-specific extraction logic
- compatibility mapping to the current DB shape
- source identity decisions

This makes multi-source expansion risky and makes the application core aware of source-specific behavior indirectly.

## 5. Source Abstraction Goals

### 5.1 FUTURE DESIGN

The Source Framework must:

- isolate source-specific HTTP and parsing logic
- support multiple vehicle/listing sources without changing business logic
- make source capabilities explicit
- make source provenance explicit
- preserve current v2.9/v3.0 compatibility behavior during migration
- provide a stable handoff boundary to future canonical modeling in ARCH-003

### 5.2 v3.0 Required

For v3.0, the Source Framework must at minimum:

- abstract AutoScout24 behind a source contract
- allow orchestration to call a registry/service rather than a hard-coded scraper module
- preserve the existing `cars` table and current scrape semantics
- preserve current sold detection behavior unless explicitly source-capability-gated

### 5.3 Future Evolution

Future source framework evolution may include:

- multiple active marketplace adapters
- incremental sync modes
- explicit source health management
- per-source throttling policies
- richer provenance persistence
- canonical mapping into the ARCH-003 model

## 6. Source Adapter / Plugin Model

### 6.1 FUTURE DESIGN

Each source is implemented as a dedicated adapter.

Examples:

- `AutoScout24SourceAdapter`
- `MobileDeSourceAdapter`
- `GaspedaalSourceAdapter`

Adapters are registered through a `SourceRegistry`, not imported ad hoc by business modules.

### 6.2 Proposed Runtime Structure

```text
sources/
    __init__.py
    base.py
    types.py
    registry.py
    policies.py
    compatibility.py
    autoscout24.py
```

### 6.3 Boundary Rule

Adapters may own:

- remote requests
- source-specific parsing
- listing discovery logic
- source-specific extraction logic
- source capabilities
- source health diagnostics

Adapters must not own:

- scoring
- deal logic
- watchlist logic
- recommendation logic
- dashboard rendering
- canonical business rules

## 7. Source Interface / Contract

### 7.1 FUTURE DESIGN

The source interface must define a stable contract between orchestration and source implementations.

Illustrative contract:

```python
class SourceAdapter(Protocol):
    def descriptor(self) -> SourceDescriptor: ...
    def capabilities(self) -> SourceCapabilities: ...

    def discover_listings(
        self,
        request: DiscoveryRequest,
        context: SourceContext,
    ) -> Iterable[DiscoveredListing]: ...

    def fetch_listing_detail(
        self,
        listing: DiscoveredListing,
        context: SourceContext,
    ) -> "SourceListingDetail | None": ...

    def fetch_description(
        self,
        listing: DiscoveredListing,
        detail: "SourceListingDetail | None",
        context: SourceContext,
    ) -> "str | None": ...

    def to_source_snapshot(
        self,
        listing: DiscoveredListing,
        detail: "SourceListingDetail | None",
        description: "str | None",
    ) -> "SourceSnapshot": ...
```

### 7.2 FUTURE DESIGN

Common responsibilities of the contract:

- source metadata
- capabilities declaration
- listing discovery
- detail retrieval
- optional description retrieval
- source snapshot generation

### 7.3 v3.0 Required

For v3.0, the contract only needs to support the current scrape flow:

- paginated discovery
- per-listing detail fetch
- optional description fetch
- compatibility handoff to current persistence

## 8. Source DTO Concepts

### 8.1 FUTURE DESIGN

The Source Framework must hand off source-owned objects, not canonical domain entities.

#### `SourceDescriptor`

Fields:

- `source_name`
- `display_name`
- `version`
- `base_url`

#### `SourceCapabilities`

Fields may include:

- `supports_listing_discovery`
- `supports_detail_fetch`
- `supports_description_fetch`
- `supports_full_inventory_scan`
- `supports_incremental_sync`
- `supports_explicit_sold_status`
- `supports_structured_options`
- `supports_rate_limit_headers`

#### `DiscoveryRequest`

Fields may include:

- query preset / market segment
- pagination policy
- scan mode
- max pages / cursor state

#### `SourceContext`

Purpose:

- carry execution-scoped information needed by source adapters during one orchestration run
- avoid leaking orchestration and request-policy concerns through unrelated global state
- provide a stable source-boundary context object without forcing adapters to know business/domain internals

It may contain:

- `run_id`
- `source_name`
- selected discovery mode
- request policy / throttling policy references
- source configuration for the active run
- dry-run flag when source behavior needs to know whether downstream writes will occur
- logger / diagnostics hooks
- per-run correlation metadata

It must not contain:

- canonical Car/domain entities
- scoring outputs
- recommendation decisions
- persistence row objects from the `cars` table
- dashboard/rendering state

Why it belongs at the source boundary:

- source adapters need execution-scoped policy and diagnostics context
- those concerns are not part of the source payload itself
- keeping them in `SourceContext` prevents accidental coupling to domain or persistence layers

#### `DiscoveredListing`

Fields:

- `source_name`
- `source_listing_id`
- `listing_url`
- `discovered_at`
- `summary_payload`
- optional `summary_hash`

#### `SourceListingDetail`

Fields:

- `source_name`
- `source_listing_id`
- `fetched_at`
- `detail_payload`

#### `SourceSnapshot`

Fields:

- `source_name`
- `source_listing_id`
- `source_url`
- `discovered_at`
- `fetched_at`
- `raw_summary_payload`
- `raw_detail_payload`
- `extracted_fields`
- `field_provenance`

#### `SourceIngestionService`

Role:

- first-class orchestration component that coordinates enabled source adapters for a pipeline run

Responsibilities:

- obtain enabled adapters from `SourceRegistry`
- execute discovery requests
- invoke detail and description retrieval according to source capabilities
- produce `SourceSnapshot` outputs
- hand those outputs to the compatibility bridge in v3.0
- surface source-level metrics, failures, and diagnostics back to orchestration

### 8.2 Boundary Rule

`SourceSnapshot` is the output of the Source Framework. It is not the canonical Car/domain model. ARCH-003 will define the domain model that consumes this snapshot.

## 9. Listing Discovery

### 9.1 CURRENT FACT

Current discovery is a full AutoScout24 page scan in [run_scraper](/opt/carhunter/v3.0-dev/scraper.py:803), using:

- hard-coded base URL: [BASE_URL](/opt/carhunter/v3.0-dev/scraper.py:14)
- fixed max pages: `PAGES = 100`
- page parser: [parse_page](/opt/carhunter/v3.0-dev/scraper.py:403)
- source filtering in scraper logic: only `variant == "Cabriolet"`

### 9.2 FUTURE DESIGN

Discovery must become a source-owned responsibility:

- source query construction
- source pagination behavior
- summary payload interpretation
- source-side listing inclusion/exclusion rules

### 9.3 v3.0 Required

v3.0 only requires full inventory scan behavior compatible with the current sold detection model.

### 9.4 Future Evolution

Future discovery modes may include:

- incremental discovery
- changed-listing sync
- multiple query presets
- source-partitioned discovery strategies

## 10. Listing Detail Retrieval

### 10.1 CURRENT FACT

Detailed retrieval is currently source-specific in [fetch_car_details](/opt/carhunter/v3.0-dev/scraper.py:238), with optional separate description retrieval in [fetch_description](/opt/carhunter/v3.0-dev/scraper.py:183).

### 10.2 FUTURE DESIGN

Detail retrieval must remain source-owned. The framework must support:

- summary-only sources
- detail-rich sources
- separate description fetches when needed
- soft-fail detail fetching per listing

### 10.3 v3.0 Required

AutoScout24 detail retrieval must preserve current extraction of:

- listing id
- title
- price
- km
- year
- color
- color_detail
- hp
- drive
- gearbox
- body_type
- upholstery
- interior_color
- options
- description

## 11. Source-Specific Normalization Boundary

### 11.1 CURRENT FACT

[normalize_car](/opt/carhunter/v3.0-dev/scraper.py:661) currently maps AutoScout24 source data directly into the current `cars`-table payload shape.

### 11.2 FUTURE DESIGN

This direct mapping must be split into two steps:

1. source-specific extraction into `SourceSnapshot`
2. downstream mapping from `SourceSnapshot` into either:
   - the current `cars` compatibility payload for v3.0
   - the future canonical model defined by ARCH-003

### 11.3 Boundary Rule

The source adapter may normalize source fields into stable extracted fields, but it must not define the detailed canonical business model.

## 12. Source Identity and Source Listing IDs

### 12.1 CURRENT FACT

Current source identity is implicit and AutoScout24-specific.

- source listing id: `autoscout_id`
- listing URL: `url`
- continuity key: `fingerprint`

### 12.2 FUTURE DESIGN

Every source record must explicitly carry:

- `source_name`
- `source_listing_id`
- `source_url`

### 12.3 v3.0 Required

AutoScout24 maps to:

- `source_name = "autoscout24"`
- `source_listing_id = autoscout_id`

### 12.4 Relationship to Duplicate Handling

ARCH-002 defines source identity only at the source boundary. Cross-source canonical identity is deferred to ARCH-003.

## 13. Source Provenance

### 13.1 CURRENT FACT

Provenance is currently implicit in:

- AutoScout24-specific URL structure
- `autoscout_id`
- discovery/detail fetch timing behavior
- `first_seen` and `last_seen`

There is no explicit persisted field-level provenance model.

### 13.2 FUTURE DESIGN

The Source Framework must attach provenance metadata to extracted fields, including:

- source name
- extraction stage (`summary`, `detail`, `description`)
- source listing id
- source URL
- fetch/discovery timestamps
- optional extraction confidence when applicable

### 13.3 v3.0 Required

For v3.0, provenance may remain in-memory at the source boundary if the current schema cannot persist all provenance metadata without disruptive changes.

## 14. Error Handling and Retry Semantics

### 14.1 CURRENT FACT

The current scraper mostly logs and returns empty values or `None`, for example in:

- [http_get](/opt/carhunter/v3.0-dev/scraper.py:72)
- [fetch_description](/opt/carhunter/v3.0-dev/scraper.py:183)
- [fetch_car_details](/opt/carhunter/v3.0-dev/scraper.py:238)

### 14.2 FUTURE DESIGN

The framework should define typed source errors, such as:

- `SourceTemporaryError`
- `SourceRateLimitError`
- `SourceContractError`
- `SourceUnavailableError`
- `SourceAuthenticationError`

### 14.3 Policy

- transient network/request failures are retryable
- parse/contract violations are non-retryable for the same payload
- per-listing detail failures are soft-fail by default
- source-wide discovery failure must be visible in pipeline results and diagnostics

### 14.4 v3.0 Required

v3.0 requires isolated source failure behavior aligned with [docs/ARCHITECTURE.md](/opt/carhunter/v3.0-dev/docs/ARCHITECTURE.md:246).

## 15. Rate Limiting and Request Policy

### 15.1 CURRENT FACT

Current request behavior uses direct `requests.get(..., timeout=30)` in [http_get](/opt/carhunter/v3.0-dev/scraper.py:72) with a static user agent.

### 15.2 FUTURE DESIGN

Each source must declare or inherit a request policy covering:

- timeout
- retry count
- retry backoff
- jitter
- concurrency limit
- minimum delay / token bucket
- user agent
- 429 and upstream throttling behavior
- degraded-mode cooldown

### 15.3 v3.0 Required

v3.0 requires at least:

- explicit timeout
- bounded retries
- no uncontrolled parallel request storms

## 16. Source Capabilities

### 16.1 FUTURE DESIGN

Source capabilities must be explicit and queryable.

Illustrative capabilities:

- `supports_listing_discovery`
- `supports_detail_fetch`
- `supports_description_fetch`
- `supports_full_inventory_scan`
- `supports_incremental_sync`
- `supports_explicit_sold_status`
- `supports_structured_options`
- `supports_price_history`
- `supports_rate_limit_headers`

### 16.2 Purpose

Capabilities let orchestration and compatibility logic choose safe behavior without hard-coding source assumptions throughout the codebase.

## 17. Source Configuration

### 17.1 CURRENT FACT

[config.py](/opt/carhunter/v3.0-dev/config.py) does not yet define a source registry or source enablement matrix. The current runtime configuration is minimal and application-wide.

### 17.2 FUTURE DESIGN

Source configuration must support:

- enabled / disabled state
- base URL
- query presets
- page/cursor limits
- request policy
- source-specific credentials if ever needed

### 17.3 v3.0 Required

v3.0 may implement source configuration as static Python configuration or registry wiring, provided it is explicit and centrally owned.

## 18. Source Lifecycle and Health

### 18.1 FUTURE DESIGN

Each source should have an operational lifecycle:

- `registered`
- `enabled`
- `active`
- `degraded`
- `paused`
- `retired`

### 18.2 Health Signals

Health may be derived from:

- repeated request failures
- parse contract failures
- sustained throttling
- empty-result anomalies
- operator disablement

### 18.3 v3.0 Required

v3.0 requires at least source-level diagnostics and clear logging when a source is degraded or unavailable.

## 19. Pipeline Integration

### 19.1 CURRENT FACT

The current scrape integration is:

- [stage_scrape](/opt/carhunter/v3.0-dev/orchestration.py:224)
- [run_scraper](/opt/carhunter/v3.0-dev/scraper.py:803)

Other source interactions occur directly in:

- [descriptions.py](/opt/carhunter/v3.0-dev/descriptions.py)
- [repair_engine.py](/opt/carhunter/v3.0-dev/repair_engine.py)
- [data_quality.py](/opt/carhunter/v3.0-dev/data_quality.py)

### 19.2 FUTURE DESIGN

The Source Framework should be invoked through a central service named `SourceIngestionService`.

```text
orchestration
    -> SourceRegistry
    -> SourceIngestionService
    -> SourceAdapter
    -> SourceSnapshot
    -> compatibility bridge / ARCH-003 canonical mapper
```

`SourceIngestionService` is responsible for orchestration-facing coordination. Individual adapters remain responsible only for source-specific behavior.

### 19.3 v3.0 Required

For v3.0:

- `scrape` stage must route through the source framework
- repair/backfill/description flows should progressively stop calling AutoScout24-specific helpers directly

## 20. Data Ownership Boundaries

### 20.1 Source Layer Owns

- source metadata
- discovery requests/results
- source listing ids
- source URLs
- raw source payloads
- source-specific extraction logic
- source provenance metadata
- request policies
- source capability declarations

### 20.2 Source Layer Must Not Own

- canonical business identity
- scoring logic
- deal logic
- watchlist logic
- recommendation logic
- dashboard/API rendering
- final domain relationships

### 20.3 Boundary with ARCH-003

ARCH-002 ends at the source-owned handoff object. ARCH-003 begins where source-originated data becomes a canonical business entity.

## 21. Interaction with ARCH-003

### 21.1 FUTURE DESIGN

ARCH-003 will define:

- canonical Car/domain entities
- cross-source identity semantics
- canonical field definitions
- canonical lifecycle/state semantics
- domain relationships

### 21.2 Deferred Questions

The following are intentionally deferred to ARCH-003:

- what the canonical aggregate contains
- how cross-source deduplication works in the target architecture
- how listings relate to vehicles, dealers, and events
- whether provenance becomes a first-class persisted domain concept

## 22. Relationship with ARCH-005

### 22.1 FUTURE DESIGN

ARCH-002 owns the vehicle/listing source adapter contract and source-specific integration.

That includes:

- source adapter responsibilities
- source DTOs and provenance
- source capability definitions
- source request and health policies
- source integration with orchestration and compatibility mapping

### 22.2 FUTURE DESIGN

ARCH-005 – Plugin Framework must not redefine the vehicle/listing source contract established here.

If ARCH-005 is retained, it should cover only cross-cutting plugin infrastructure concerns such as:

- generic plugin loading conventions
- registration mechanics shared beyond sources
- plugin packaging/discovery rules
- lifecycle hooks common to multiple plugin families

### 22.3 Boundary Rule

If a concept is specific to vehicle/listing acquisition, source identity, source provenance, or source fetch behavior, it belongs in ARCH-002, not ARCH-005.

## 23. Backward Compatibility with the Current `cars` Table

### 22.1 CURRENT FACT

The current persistence contract is the flat payload consumed by [save_car](/opt/carhunter/v3.0-dev/database.py:265).

### 22.2 FUTURE DESIGN

v3.0 requires a compatibility bridge that translates `SourceSnapshot` into the current `cars`-table payload.

Illustrative responsibility:

```text
SourceSnapshot
    -> CurrentCarsCompatibilityBridge
    -> legacy save_car payload
    -> database.save_car
```

### 22.3 Compatibility Rule

The framework must preserve current behavior for:

- `autoscout_id`
- `fingerprint`
- `url`
- `first_seen`
- `last_seen`
- `sold` / `sold_at`
- `last_price`
- `price_drop`

### 22.4 v3.0 Required

Single-source compatibility mode must remain operational without requiring a full schema redesign.

## 24. Migration Path from the Current AutoScout24 Scraper

### Phase 0 – CURRENT FACT

AutoScout24 behavior is implemented directly in [scraper.py](/opt/carhunter/v3.0-dev/scraper.py).

### Phase 1 – v3.0 Required

- introduce `SourceRegistry`
- introduce `SourceAdapter` contract
- wrap current AutoScout24 implementation as `AutoScout24SourceAdapter`
- preserve [database.save_car](/opt/carhunter/v3.0-dev/database.py:265)
- add `CurrentCarsCompatibilityBridge`
- route [stage_scrape](/opt/carhunter/v3.0-dev/orchestration.py:224) through the source framework

### Phase 2 – v3.x Near-Term

- route description refresh through the adapter
- route repair and backfill fetches through the adapter
- centralize URL normalization and request policy in the source layer

### Phase 3 – Future Evolution

- hand off `SourceSnapshot` into the canonical model defined by ARCH-003
- reduce reliance on the legacy `cars`-table payload contract
- enable additional sources under the same framework

## 25. Testing Strategy

### 24.1 CURRENT FACT

Relevant current tests include:

- [tests/test_orchestration.py](/opt/carhunter/v3.0-dev/tests/test_orchestration.py)
- [tests/test_sold_detection.py](/opt/carhunter/v3.0-dev/tests/test_sold_detection.py)
- [tests/test_data_quality.py](/opt/carhunter/v3.0-dev/tests/test_data_quality.py)
- [tests/test_repair_engine.py](/opt/carhunter/v3.0-dev/tests/test_repair_engine.py)

### 24.2 FUTURE DESIGN

The Source Framework should add:

- adapter contract tests
- discovery fixture tests
- detail extraction fixture tests
- compatibility parity tests against current AutoScout24 behavior
- orchestration tests with source registry mocking
- source failure isolation tests
- sold-detection compatibility tests

### 24.3 v3.0 Required

v3.0 must prove that the AutoScout24 adapter preserves the current scrape-to-save behavior under the compatibility bridge.

## 26. Security Considerations

### 25.1 FUTURE DESIGN

The Source Framework must enforce:

- no credentials embedded in source code
- controlled source configuration
- defensive parsing of remote payloads
- bounded timeouts and retries
- no uncontrolled outbound request fan-out
- sanitized logging for sensitive request metadata

### 25.2 CURRENT FACT

Telegram secrets already come from `.env` in [telegram.py](/opt/carhunter/v3.0-dev/telegram.py), demonstrating the preferred pattern for secrets separation.

## 27. Observability Requirements

### 26.1 CURRENT FACT

Logging today is plain-text file and console logging in [debug.py](/opt/carhunter/v3.0-dev/debug.py).

### 26.2 FUTURE DESIGN

The Source Framework must emit source-oriented diagnostics including:

- source name
- scan mode
- pages fetched
- listings discovered
- details fetched
- retries performed
- throttle events
- parse failures
- degraded/paused state transitions

### 26.3 v3.0 Required

Even if logs remain text-based in v3.0, source-related events must be explicit and consistent enough to support operational debugging.

## 28. Architectural Constraints

ARCH-002 must preserve the following constraints:

- compatibility-first evolution from [docs/ARCHITECTURE.md](/opt/carhunter/v3.0-dev/docs/ARCHITECTURE.md)
- current SQLite-based runtime
- current orchestration entrypoint in [orchestration.py](/opt/carhunter/v3.0-dev/orchestration.py)
- current `cars`-table continuity semantics
- current scrape-driven sold detection behavior unless source capabilities allow a better strategy
- current user-visible ranking, deal, watchlist, and notification behavior during migration

## 29. Explicit Non-Goals

ARCH-002 explicitly does not define:

- the canonical Car/domain model in detail
- the final multi-entity persistence schema
- dealer/domain aggregates
- pricing-history schema
- recommendation architecture redesign
- scoring architecture redesign
- REST API architecture
- PostgreSQL migration architecture

## 30. Open Questions Deferred to ARCH-003

- What is the canonical boundary between `Vehicle`, `Listing`, `Dealer`, `Score`, and `Recommendation`?
- What is the authoritative canonical identity across multiple sources?
- Which fields become canonical, optional, derived, or source-scoped?
- How is provenance represented in the canonical model and persisted schema?
- How are duplicate listings, relistings, and historical events represented in the domain model?

## 31. Summary

ARCH-002 defines the Source Framework boundary for CarHunter v3.

The framework must:

- abstract source-specific behavior behind adapters
- keep source concerns out of core business logic
- expose source identity, provenance, capabilities, and request policy explicitly
- integrate cleanly with orchestration
- preserve the current `cars` table through a compatibility bridge
- create a clean handoff into the future canonical model defined by ARCH-003

This preserves current operational behavior while enabling controlled evolution from a single AutoScout24 scraper into a multi-source architecture.
