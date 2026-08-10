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
        ingestion_result = SourceIngestionResult(
            source_name="autoscout24",
            snapshots=[mock.sentinel.snapshot],
            active_fingerprints=["fp-1"],
        )

        with mock.patch(
            "sources.build_default_source_registry",
            return_value=mock.sentinel.registry,
        ) as build_registry, mock.patch(
            "sources.SourceIngestionService",
        ) as service_cls, mock.patch(
            "source_compatibility.apply_compatibility_inventory_updates",
            return_value=mock.Mock(new_cars=3, not_available_anymore=1),
        ) as apply_updates, mock.patch(
            "source_compatibility.should_fetch_detail_for_listing",
            mock.sentinel.should_fetch_detail,
        ), mock.patch(
            "scraper.run_scraper",
        ) as run_scraper:
            service_cls.return_value.ingest_full_inventory.return_value = ingestion_result
            context = orchestration.PipelineContext(mode="full")
            orchestration.stage_scrape(context)

        build_registry.assert_called_once_with()
        service_cls.assert_called_once_with(mock.sentinel.registry)
        service_cls.return_value.ingest_full_inventory.assert_called_once_with(
            source_name="autoscout24",
            should_fetch_detail=mock.sentinel.should_fetch_detail,
        )
        apply_updates.assert_called_once_with(
            ingestion_result.snapshots,
            ingestion_result.active_fingerprints,
            dry_run=False,
        )
        run_scraper.assert_not_called()
        self.assertEqual(context.stage_results["new_cars"], 3)
        self.assertEqual(context.stage_results["not_available_anymore"], 1)
