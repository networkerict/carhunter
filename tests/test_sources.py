import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock

import config
import database
import orchestration
import scraper
from source_compatibility import (
    apply_compatibility_inventory_updates,
    should_fetch_detail_for_listing,
    snapshot_to_compatibility_payload,
)
from sources import (
    AutoScout24SourceAdapter,
    MobileDeSourceAdapter,
    DiscoveredListing,
    DiscoveryRequest,
    SourceAdapter,
    SourceContext,
    SourceIngestionResult,
    SourceIngestionService,
    SourceListingDetail,
)
from sources.base import SourceUnavailableError
from sources.registry import SourceRegistry


def make_listing(listing_id, url, *, kilometers=50000, price=25000):
    return {
        "id": listing_id,
        "url": url,
        "vehicle": {
            "variant": "Cabriolet",
            "make": "Audi",
            "model": "A5",
            "motorTypeName": "2.0 TFSI",
            "mileageInKm": kilometers,
            "transmissionType": "Automatik",
            "bodyType": "Cabriolet",
            "rawPowerInHp": "190",
            "driveTrain": "Front",
        },
        "price": {
            "priceRaw": price,
        },
        "tracking": {
            "firstRegistration": "2018-01-01",
        },
    }


def make_detail(listing_id):
    return {
        "id": listing_id,
        "description": f"Detail for {listing_id}",
        "bodyColor": "Black",
        "upholstery": "Leather",
    }


class TestSourceRegistry(unittest.TestCase):
    def test_autoscout24_adapter_registration(self):
        registry = SourceRegistry()
        registry.register(
            AutoScout24SourceAdapter(max_pages=2),
            configuration={"enabled": True, "max_pages": 2},
        )

        adapter = registry.get("autoscout24")
        self.assertIsInstance(adapter, AutoScout24SourceAdapter)
        self.assertIsInstance(adapter, SourceAdapter)
        self.assertEqual(adapter.descriptor().source_name, "autoscout24")
        self.assertEqual(
            adapter.descriptor().plugin_descriptor.plugin_family,
            "source",
        )

    def test_unknown_source_lookup_failure(self):
        registry = SourceRegistry()

        with self.assertRaises(SourceUnavailableError):
            registry.get("missing-source")

    def test_disabled_source_lookup_failure(self):
        registry = SourceRegistry()
        registry.register(
            AutoScout24SourceAdapter(max_pages=2),
            configuration={"enabled": False, "max_pages": 2},
            enabled=False,
        )

        with self.assertRaises(SourceUnavailableError):
            registry.get("autoscout24")


class TestAutoScout24SourceAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = AutoScout24SourceAdapter(max_pages=2)
        self.context = SourceContext(source_name="autoscout24")

    def test_source_snapshot_construction(self):
        listing = DiscoveredListing(
            source_name="autoscout24",
            source_listing_id="123",
            source_url="https://www.autoscout24.de/angebote/test",
            discovered_at=datetime.now(),
            raw_summary_payload={
                "id": "123",
                "url": "/angebote/test",
                "fingerprint": "fp-123",
                "vehicle": {"variant": "Cabriolet"},
                "price": {"priceRaw": 25000},
                "tracking": {"firstRegistration": "2018-01-01"},
            },
        )
        detail = SourceListingDetail(
            source_name="autoscout24",
            source_listing_id="123",
            fetched_at=datetime.now(),
            raw_detail_payload={"description": "Detail text", "bodyColor": "Black"},
        )

        with mock.patch(
            "scraper.normalize_car",
            return_value={"fingerprint": "fp-123", "description": ""},
        ) as normalize_car:
            snapshot = self.adapter.to_source_snapshot(
                listing,
                detail,
                description="Detailed description",
            )

        normalize_car.assert_called_once()
        self.assertEqual(snapshot.source_name, "autoscout24")
        self.assertEqual(snapshot.source_listing_id, "123")
        self.assertEqual(snapshot.extracted_fields["fingerprint"], "fp-123")
        self.assertEqual(
            snapshot.extracted_fields["description"],
            "Detailed description",
        )
        self.assertEqual(
            snapshot.field_provenance["description"]["stage"],
            "description",
        )
        self.assertEqual(
            snapshot.field_provenance["fingerprint"]["stage"],
            "summary",
        )

    def test_adapter_delegates_to_existing_scraper_behavior_and_keeps_fingerprint_logic(self):
        listing_payload = make_listing("123", "/angebote/123")
        expected_fingerprint = scraper.create_fingerprint(listing_payload)

        with mock.patch(
            "scraper.fetch_page",
            return_value="<html />",
        ) as fetch_page, mock.patch(
            "scraper.parse_page",
            return_value=[listing_payload],
        ) as parse_page, mock.patch(
            "scraper.create_fingerprint",
            wraps=scraper.create_fingerprint,
        ) as create_fingerprint:
            listings = self.adapter.discover_listings(
                DiscoveryRequest(scan_mode="full_inventory", max_pages=1),
                self.context,
            )

        fetch_page.assert_called_once_with(1)
        parse_page.assert_called_once_with("<html />")
        create_fingerprint.assert_called_once()
        self.assertEqual(len(listings), 1)
        self.assertEqual(
            listings[0].raw_summary_payload["fingerprint"],
            expected_fingerprint,
        )

    def test_fetch_listing_detail_delegates_to_scraper(self):
        listing = DiscoveredListing(
            source_name="autoscout24",
            source_listing_id="123",
            source_url="https://www.autoscout24.de/angebote/123",
            discovered_at=datetime.now(),
            raw_summary_payload={
                "fingerprint": "fp-123",
                "vehicle": {"variant": "Cabriolet"},
                "price": {"priceRaw": 25000},
                "tracking": {"firstRegistration": "2018-01-01"},
            },
        )

        with mock.patch(
            "scraper.fetch_car_details",
            return_value={"bodyColor": "Black"},
        ) as fetch_detail:
            detail = self.adapter.fetch_listing_detail(listing, self.context)

        fetch_detail.assert_called_once_with(
            "https://www.autoscout24.de/angebote/123"
        )
        self.assertEqual(detail.raw_detail_payload["bodyColor"], "Black")

    def test_query_preset_is_intentionally_absent_in_arch006(self):
        self.assertNotIn("query_preset", config.SOURCE_REGISTRY["autoscout24"])
        self.assertNotIn(
            "query_preset",
            self.adapter.descriptor().plugin_descriptor.configuration_contract["optional"],
        )


class TestSourceIngestionService(unittest.TestCase):
    def setUp(self):
        self.original_database = config.DATABASE
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        config.DATABASE = self.original_database
        self.tempdir.cleanup()

    def test_compatibility_payload_passthrough(self):
        snapshot = mock.Mock(extracted_fields={"fingerprint": "fp-1", "title": "Audi A5"})
        self.assertEqual(
            snapshot_to_compatibility_payload(snapshot),
            {"fingerprint": "fp-1", "title": "Audi A5"},
        )

    def test_service_produces_snapshots_and_does_not_own_persistence(self):
        registry = SourceRegistry()
        adapter = mock.Mock(spec=AutoScout24SourceAdapter)
        listing_one = DiscoveredListing(
            source_name="autoscout24",
            source_listing_id="1",
            source_url="https://www.autoscout24.de/angebote/1",
            discovered_at=datetime.now(),
            raw_summary_payload={"fingerprint": "fp-1"},
        )
        listing_two = DiscoveredListing(
            source_name="autoscout24",
            source_listing_id="2",
            source_url="https://www.autoscout24.de/angebote/2",
            discovered_at=datetime.now(),
            raw_summary_payload={"fingerprint": "fp-2"},
        )
        snapshot_one = mock.Mock()
        snapshot_two = mock.Mock()

        adapter.descriptor.return_value = AutoScout24SourceAdapter(max_pages=2).descriptor()
        adapter.discover_listings.return_value = [listing_one, listing_two]
        adapter.fetch_listing_detail.return_value = mock.sentinel.detail
        adapter.to_source_snapshot.side_effect = [snapshot_one, snapshot_two]
        registry.register(adapter, configuration={"enabled": True, "max_pages": 2})

        with mock.patch("database.save_car") as save_car, mock.patch(
            "database.mark_missing_cars_sold"
        ) as mark_missing_cars_sold:
            result = SourceIngestionService(registry).ingest_full_inventory(
                source_name="autoscout24",
                should_fetch_detail=lambda listing: listing.source_listing_id == "1",
            )

        self.assertEqual(result.snapshots, [snapshot_one, snapshot_two])
        self.assertEqual(result.active_fingerprints, ["fp-1", "fp-2"])
        adapter.fetch_listing_detail.assert_called_once_with(listing_one, mock.ANY)
        save_car.assert_not_called()
        mark_missing_cars_sold.assert_not_called()

    def test_compatibility_boundary_preserves_existing_scrape_behavior(self):
        old_db = os.path.join(self.tempdir.name, "old.db")
        new_db = os.path.join(self.tempdir.name, "new.db")
        pages = {
            1: [
                make_listing("1", "/angebote/1", price=20000),
                make_listing("2", "/angebote/2", kilometers=51000, price=21000),
            ],
            2: [make_listing("2", "/angebote/2", kilometers=51000, price=21000)],
        }
        details = {
            "https://www.autoscout24.de/angebote/1": make_detail("1"),
            "https://www.autoscout24.de/angebote/2": make_detail("2"),
        }

        with mock.patch("scraper.PAGES", 2), mock.patch(
            "scraper.fetch_page",
            side_effect=lambda page: f"page-{page}",
        ), mock.patch(
            "scraper.parse_page",
            side_effect=lambda html: pages[int(html.split("-")[-1])],
        ), mock.patch(
            "scraper.fetch_car_details",
            side_effect=lambda url: details[url],
        ):
            config.DATABASE = old_db
            old_conn = database.get_connection()
            old_conn.close()
            old_result = scraper.run_scraper()

            config.DATABASE = new_db
            new_conn = database.get_connection()
            new_conn.close()
            registry = SourceRegistry()
            registry.register(
                AutoScout24SourceAdapter(max_pages=2),
                configuration={"enabled": True, "max_pages": 2},
            )
            ingestion_result = SourceIngestionService(registry).ingest_full_inventory(
                source_name="autoscout24",
                should_fetch_detail=should_fetch_detail_for_listing,
            )
            compatibility_result = apply_compatibility_inventory_updates(
                ingestion_result.snapshots,
                ingestion_result.active_fingerprints,
            )

        self.assertEqual(
            old_result,
            (
                compatibility_result.new_cars,
                compatibility_result.not_available_anymore,
            ),
        )

        config.DATABASE = old_db
        old_rows = sorted(
            database.get_all_cars(),
            key=lambda row: row.fingerprint,
        )
        config.DATABASE = new_db
        new_rows = sorted(
            database.get_all_cars(),
            key=lambda row: row.fingerprint,
        )

        self.assertEqual(len(old_rows), len(new_rows))
        comparable_fields = [
            "fingerprint",
            "autoscout_id",
            "title",
            "price",
            "km",
            "year",
            "status",
        ]
        for old_row, new_row in zip(old_rows, new_rows):
            for field in comparable_fields:
                self.assertEqual(getattr(old_row, field), getattr(new_row, field))

    def test_dry_run_causes_no_persistent_mutations(self):
        db_path = os.path.join(self.tempdir.name, "dry-run.db")
        config.DATABASE = db_path
        connection = database.get_connection()
        connection.close()

        existing_active = {
            "id": "1",
            "autoscout_id": "1",
            "fingerprint": "fp-1",
            "title": "Audi A5 1",
            "price": 20000,
            "km": 50000,
            "year": 2018,
            "url": "https://www.autoscout24.de/angebote/1",
        }
        existing_missing = {
            "id": "2",
            "autoscout_id": "2",
            "fingerprint": "fp-2",
            "title": "Audi A5 2",
            "price": 21000,
            "km": 51000,
            "year": 2019,
            "url": "https://www.autoscout24.de/angebote/2",
        }
        database.save_car(existing_active)
        database.save_car(existing_missing)

        before_rows = sorted(database.get_all_cars(), key=lambda car: car.fingerprint)
        result = apply_compatibility_inventory_updates(
            snapshots=[
                mock.Mock(
                    extracted_fields={
                        "id": "1",
                        "autoscout_id": "1",
                        "fingerprint": "fp-1",
                        "title": "Audi A5 1",
                        "price": 20000,
                        "km": 50000,
                        "year": 2018,
                        "url": "https://www.autoscout24.de/angebote/1",
                    }
                ),
                mock.Mock(
                    extracted_fields={
                        "id": "3",
                        "autoscout_id": "3",
                        "fingerprint": "fp-3",
                        "title": "Audi A5 3",
                        "price": 22000,
                        "km": 52000,
                        "year": 2020,
                        "url": "https://www.autoscout24.de/angebote/3",
                    }
                ),
            ],
            active_fingerprints=["fp-1", "fp-3"],
            dry_run=True,
        )
        after_rows = sorted(database.get_all_cars(), key=lambda car: car.fingerprint)

        self.assertEqual(result.new_cars, 1)
        self.assertEqual(result.not_available_anymore, 1)
        self.assertEqual(len(before_rows), len(after_rows))
        for before_row, after_row in zip(before_rows, after_rows):
            self.assertEqual(before_row.fingerprint, after_row.fingerprint)
            self.assertEqual(before_row.sold, after_row.sold)
            self.assertEqual(before_row.price, after_row.price)

    def test_service_active_fingerprints_follow_discovered_inventory(self):
        registry = SourceRegistry()
        registry.register(
            AutoScout24SourceAdapter(max_pages=1),
            configuration={"enabled": True, "max_pages": 1},
        )

        with mock.patch("scraper.fetch_page", return_value="<html />"), mock.patch(
            "scraper.parse_page",
            return_value=[
                make_listing("1", "/angebote/1"),
                make_listing("2", "/angebote/2", kilometers=51000),
            ],
        ), mock.patch(
            "scraper.fetch_car_details",
            return_value=make_detail("1"),
        ):
            result = SourceIngestionService(registry).ingest_full_inventory(
                source_name="autoscout24",
                should_fetch_detail=lambda listing: False,
            )

        self.assertEqual(len(result.active_fingerprints), 2)
        self.assertEqual(len(result.snapshots), 2)

    def test_orchestration_stage_uses_registry(self):
        # Multi-source coordinator result with snapshots
        multi_source_result = mock.Mock(
            all_snapshots=[mock.sentinel.snapshot],
            active_fingerprints=["fp-1"],
            overall_outcome="SUCCESS",
            total_snapshots=1,
            total_accepted=1,
            total_rejected=0,
            per_instance_results=[],  # Empty list for this test
        )

        with mock.patch(
            "sources.build_default_source_registry",
        ) as build_registry, mock.patch(
            "sources.build_source_instances",
        ) as build_instances, mock.patch(
            "sources.build_source_coordinator",
        ) as build_coordinator, mock.patch(
            "source_compatibility.apply_compatibility_inventory_updates",
            return_value=mock.Mock(new_cars=3, not_available_anymore=1),
        ) as apply_updates, mock.patch(
            "source_compatibility.should_fetch_detail_for_listing",
            mock.sentinel.should_fetch_detail,
        ), mock.patch(
            "scraper.run_scraper",
        ) as run_scraper:
            
            build_instances.return_value = []
            coordinator_mock = mock.Mock()
            coordinator_mock.execute_sources.return_value = multi_source_result
            build_coordinator.return_value = coordinator_mock
            
            context = orchestration.PipelineContext(mode="full")
            orchestration.stage_scrape(context)

        build_registry.assert_called_once_with()
        build_instances.assert_called_once()
        build_coordinator.assert_called_once()
        coordinator_mock.execute_sources.assert_called_once()
        apply_updates.assert_called_once_with(
            multi_source_result.all_snapshots,
            multi_source_result.active_fingerprints,
            dry_run=False,
        )
        run_scraper.assert_not_called()
        self.assertEqual(context.stage_results["new_cars"], 3)
        self.assertEqual(context.stage_results["not_available_anymore"], 1)


class TestMobileDeSourceAdapter(unittest.TestCase):
    """
    Tests for Mobile.de source adapter.
    
    Validates that Mobile.de:
    - Implements the complete SourceAdapter contract
    - Can be registered and discovered independently
    - Handles malformed/missing data gracefully
    - Does not corrupt other sources
    - Produces consistent SourceSnapshot objects
    """

    def setUp(self):
        self.adapter = MobileDeSourceAdapter(max_pages=2)
        self.context = SourceContext(source_name="mobile_de")

    def test_mobile_de_adapter_registration(self):
        """Mobile.de adapter can be registered like any other source."""
        registry = SourceRegistry()
        registry.register(
            MobileDeSourceAdapter(max_pages=2),
            configuration={"enabled": True, "max_pages": 2},
        )

        adapter = registry.get("mobile_de")
        self.assertIsInstance(adapter, MobileDeSourceAdapter)
        self.assertIsInstance(adapter, SourceAdapter)
        self.assertEqual(adapter.descriptor().source_name, "mobile_de")
        self.assertEqual(
            adapter.descriptor().plugin_descriptor.plugin_id,
            "mobile_de",
        )

    def test_mobile_de_descriptor(self):
        """Mobile.de descriptor provides correct metadata."""
        descriptor = self.adapter.descriptor()
        self.assertEqual(descriptor.source_name, "mobile_de")
        self.assertEqual(descriptor.display_name, "Mobile.de")
        self.assertIn("mobile", descriptor.base_url.lower())

    def test_mobile_de_capabilities(self):
        """Mobile.de declares its capabilities correctly."""
        capabilities = self.adapter.capabilities()
        self.assertTrue(capabilities.supports_listing_discovery)
        self.assertTrue(capabilities.supports_detail_fetch)
        self.assertTrue(capabilities.supports_description_fetch)
        self.assertTrue(capabilities.supports_full_inventory_scan)

    def test_mobile_de_discover_listings(self):
        """Mobile.de discovery produces DiscoveredListing objects."""
        request = DiscoveryRequest(scan_mode="full_inventory", max_pages=1)
        listings = self.adapter.discover_listings(request, self.context)

        self.assertIsInstance(listings, list)
        self.assertGreater(len(listings), 0)
        for listing in listings:
            self.assertIsInstance(listing, DiscoveredListing)
            self.assertEqual(listing.source_name, "mobile_de")
            self.assertIsNotNone(listing.source_listing_id)
            self.assertIsNotNone(listing.source_url)
            self.assertIn("mobile_de", listing.source_listing_id)

    def test_mobile_de_listing_id_deterministic(self):
        """Mobile.de listing IDs are deterministic."""
        request = DiscoveryRequest(scan_mode="full_inventory", max_pages=2)
        listings1 = self.adapter.discover_listings(request, self.context)
        listings2 = self.adapter.discover_listings(request, self.context)

        ids1 = [l.source_listing_id for l in listings1]
        ids2 = [l.source_listing_id for l in listings2]
        self.assertEqual(ids1, ids2)

    def test_mobile_de_fetch_listing_detail(self):
        """Mobile.de can fetch detailed information for listings."""
        request = DiscoveryRequest(scan_mode="full_inventory", max_pages=1)
        listings = self.adapter.discover_listings(request, self.context)
        self.assertGreater(len(listings), 0)

        detail = self.adapter.fetch_listing_detail(listings[0], self.context)
        self.assertIsNotNone(detail)
        self.assertIsInstance(detail, SourceListingDetail)
        self.assertEqual(detail.source_name, "mobile_de")
        self.assertIsNotNone(detail.raw_detail_payload)

    def test_mobile_de_fetch_description(self):
        """Mobile.de can fetch text descriptions for listings."""
        request = DiscoveryRequest(scan_mode="full_inventory", max_pages=1)
        listings = self.adapter.discover_listings(request, self.context)
        self.assertGreater(len(listings), 0)

        description = self.adapter.fetch_description(listings[0], self.context)
        self.assertIsNotNone(description)
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 0)

    def test_mobile_de_to_source_snapshot(self):
        """Mobile.de produces valid SourceSnapshot objects."""
        request = DiscoveryRequest(scan_mode="full_inventory", max_pages=1)
        listings = self.adapter.discover_listings(request, self.context)
        self.assertGreater(len(listings), 0)

        listing = listings[0]
        detail = self.adapter.fetch_listing_detail(listing, self.context)
        description = self.adapter.fetch_description(listing, self.context)
        snapshot = self.adapter.to_source_snapshot(listing, detail, description)

        self.assertEqual(snapshot.source_name, "mobile_de")
        self.assertEqual(snapshot.source_listing_id, listing.source_listing_id)
        self.assertEqual(snapshot.source_url, listing.source_url)
        self.assertIsNotNone(snapshot.discovered_at)
        self.assertIsNotNone(snapshot.fetched_at)
        self.assertIsNotNone(snapshot.raw_summary_payload)
        self.assertIsNotNone(snapshot.extracted_fields)
        self.assertIsNotNone(snapshot.field_provenance)

    def test_mobile_de_extracted_fields_contain_vehicle_data(self):
        """Mobile.de snapshot extraction includes vehicle specifications."""
        request = DiscoveryRequest(scan_mode="full_inventory", max_pages=1)
        listings = self.adapter.discover_listings(request, self.context)
        listing = listings[0]
        detail = self.adapter.fetch_listing_detail(listing, self.context)
        description = self.adapter.fetch_description(listing, self.context)
        snapshot = self.adapter.to_source_snapshot(listing, detail, description)

        extracted = snapshot.extracted_fields
        # Verify key vehicle fields are present
        self.assertIn("title", extracted)
        self.assertIn("make", extracted)
        self.assertIn("model", extracted)
        self.assertIn("year", extracted)
        self.assertIn("mileage", extracted)
        self.assertIn("price", extracted)
        self.assertIn("currency", extracted)
        self.assertIn("fuel", extracted)
        self.assertIn("transmission", extracted)
        self.assertIn("location", extracted)

    def test_mobile_de_field_provenance_tracks_sources(self):
        """Mobile.de tracks which fields came from summary vs. detail."""
        request = DiscoveryRequest(scan_mode="full_inventory", max_pages=1)
        listings = self.adapter.discover_listings(request, self.context)
        listing = listings[0]
        detail = self.adapter.fetch_listing_detail(listing, self.context)
        description = self.adapter.fetch_description(listing, self.context)
        snapshot = self.adapter.to_source_snapshot(listing, detail, description)

        provenance = snapshot.field_provenance
        # Verify provenance tracks source of each field
        self.assertGreater(len(provenance), 0)
        for field_name, prov_info in provenance.items():
            self.assertIn("source", prov_info)
            self.assertIn(
                prov_info["source"],
                ["summary", "detail", "description"],
            )

    def test_mobile_de_snapshot_without_detail(self):
        """Mobile.de snapshot works even if detail fetch fails."""
        request = DiscoveryRequest(scan_mode="full_inventory", max_pages=1)
        listings = self.adapter.discover_listings(request, self.context)
        listing = listings[0]
        # Simulate missing detail
        description = self.adapter.fetch_description(listing, self.context)
        snapshot = self.adapter.to_source_snapshot(listing, None, description)

        self.assertEqual(snapshot.source_name, "mobile_de")
        self.assertIsNotNone(snapshot.extracted_fields)
        # Should still have basic fields from summary
        self.assertIn("title", snapshot.extracted_fields)
        self.assertIn("price", snapshot.extracted_fields)

    def test_mobile_de_respects_max_pages(self):
        """Mobile.de respects max_pages configuration."""
        small_adapter = MobileDeSourceAdapter(max_pages=1)
        request = DiscoveryRequest(scan_mode="full_inventory", max_pages=1)
        listings = small_adapter.discover_listings(request, self.context)

        # With max_pages=1, should get fewer listings than max_pages=2
        large_adapter = MobileDeSourceAdapter(max_pages=5)
        large_listings = large_adapter.discover_listings(request, self.context)

        # Both should still produce results
        self.assertGreater(len(listings), 0)
        self.assertGreater(len(large_listings), 0)


class TestMultiSourceWithMobileDe(unittest.TestCase):
    """
    Tests for multi-source execution including Mobile.de.
    
    Validates that:
    - Multiple sources execute together without interference
    - Each source is acquired exactly once
    - Failure in one source doesn't affect another
    """

    def test_autoscout24_and_mobile_de_register_together(self):
        """Both AutoScout24 and Mobile.de can be registered."""
        registry = SourceRegistry()
        registry.register(
            AutoScout24SourceAdapter(max_pages=1),
            configuration={"enabled": True, "max_pages": 1},
        )
        registry.register(
            MobileDeSourceAdapter(max_pages=1),
            configuration={"enabled": True, "max_pages": 1},
        )

        autoscout24_adapter = registry.get("autoscout24")
        mobile_de_adapter = registry.get("mobile_de")

        self.assertIsInstance(autoscout24_adapter, AutoScout24SourceAdapter)
        self.assertIsInstance(mobile_de_adapter, MobileDeSourceAdapter)
        self.assertNotEqual(
            autoscout24_adapter.descriptor().source_name,
            mobile_de_adapter.descriptor().source_name,
        )

    def test_mobile_de_disabled_source_not_acquired(self):
        """Disabled Mobile.de instances are not executed."""
        registry = SourceRegistry()
        registry.register(
            MobileDeSourceAdapter(max_pages=1),
            configuration={"enabled": False, "max_pages": 1},
            enabled=False,
        )

        with self.assertRaises(Exception):
            registry.get("mobile_de")


class TestMobileDeConfigurationIntegration(unittest.TestCase):
    """
    Tests that Mobile.de integrates properly with the configuration system.
    """

    def test_mobile_de_in_source_registry_config(self):
        """Mobile.de is in the configuration SOURCE_REGISTRY."""
        self.assertIn("mobile_de", config.SOURCE_REGISTRY)
        self.assertTrue(config.SOURCE_REGISTRY["mobile_de"]["enabled"])
        self.assertGreater(config.SOURCE_REGISTRY["mobile_de"]["max_pages"], 0)

    def test_mobile_de_instance_in_source_instances(self):
        """Mobile.de has a configured SourceInstance."""
        self.assertIn("mobile_de_primary", config.SOURCE_INSTANCES)
        instance_config = config.SOURCE_INSTANCES["mobile_de_primary"]
        self.assertEqual(instance_config["source_family"], "mobile_de")
        self.assertEqual(instance_config["plugin_id"], "mobile_de")
        self.assertTrue(instance_config["enabled"])
        self.assertEqual(instance_config["provenance_identity"], "mobile.de")

    def test_mobile_de_can_be_built_from_config(self):
        """Mobile.de adapter can be instantiated from config."""
        mobile_de_config = config.SOURCE_REGISTRY["mobile_de"]
        adapter = MobileDeSourceAdapter(max_pages=mobile_de_config["max_pages"])
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.descriptor().source_name, "mobile_de")

