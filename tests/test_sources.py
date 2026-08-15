import json
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
    SourceSnapshot,
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
        snapshot = mock.Mock(extracted_fields={"fingerprint": "fp-1", "title": "Audi A5"}, source_url="")
        self.assertEqual(
            snapshot_to_compatibility_payload(snapshot),
            {"fingerprint": "fp-1", "title": "Audi A5"},
        )

    def test_compatibility_payload_normalises_mileage_to_km(self):
        # Adapters that emit "mileage" (not "km") must still populate cars.km.
        snapshot = mock.Mock(
            extracted_fields={"mileage": 10769, "title": "Audi A5"},
            source_url="",
        )
        payload = snapshot_to_compatibility_payload(snapshot)
        self.assertEqual(payload["km"], 10769)
        self.assertEqual(payload["mileage"], 10769)  # original key preserved

    def test_compatibility_payload_km_takes_precedence_over_mileage(self):
        # When "km" is already set it must not be overwritten by "mileage".
        snapshot = mock.Mock(
            extracted_fields={"km": 50000, "mileage": 99999},
            source_url="",
        )
        payload = snapshot_to_compatibility_payload(snapshot)
        self.assertEqual(payload["km"], 50000)

    def test_compatibility_payload_injects_source_url_as_url(self):
        # Adapters that expose source_url but no "url" key must populate cars.url.
        snapshot = mock.Mock(
            extracted_fields={"title": "Audi A5"},
            source_url="https://suche.pkw.de/fahrzeuge/details/123",
        )
        payload = snapshot_to_compatibility_payload(snapshot)
        self.assertEqual(payload["url"], "https://suche.pkw.de/fahrzeuge/details/123")

    def test_compatibility_payload_existing_url_not_overwritten(self):
        # When the adapter already provides a "url" key it must not be replaced.
        snapshot = mock.Mock(
            extracted_fields={"url": "https://example.com/existing"},
            source_url="https://should.not.win/",
        )
        payload = snapshot_to_compatibility_payload(snapshot)
        self.assertEqual(payload["url"], "https://example.com/existing")

    def test_compatibility_payload_autoscout24_unchanged(self):
        # AutoScout24 uses "km" and "url" directly — must not be affected.
        snapshot = mock.Mock(
            extracted_fields={
                "km": 121133,
                "url": "https://www.autoscout24.de/angebote/listing-abc",
                "fingerprint": "fp-as24",
            },
            source_url="https://www.autoscout24.de/angebote/listing-abc",
        )
        payload = snapshot_to_compatibility_payload(snapshot)
        self.assertEqual(payload["km"], 121133)
        self.assertEqual(payload["url"], "https://www.autoscout24.de/angebote/listing-abc")

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

    def test_canonical_source_snapshot_persistence_preserves_identity_and_provenance(self):
        db_path = os.path.join(self.tempdir.name, "canonical.db")
        config.DATABASE = db_path
        database.get_connection().close()

        snapshot = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="listing-123",
            source_url="https://www.autoscout24.de/angebote/listing-123",
            discovered_at=datetime.now(),
            fetched_at=datetime.now(),
            raw_summary_payload={"id": "listing-123", "title": "Audi A5"},
            raw_detail_payload={"description": "Nice car"},
            extracted_fields={"fingerprint": "fp-123", "price": 25000},
            field_provenance={
                "fingerprint": {"source_name": "autoscout24", "source_listing_id": "listing-123", "stage": "summary"},
                "price": {"source_name": "autoscout24", "source_listing_id": "listing-123", "stage": "summary"},
            },
        )

        row_id = database.save_source_snapshot(snapshot)
        self.assertIsNotNone(row_id)

        conn = database.get_connection()
        try:
            source_row = conn.execute("SELECT id, source_name FROM sources WHERE source_name = ?", ("autoscout24",)).fetchone()
            self.assertIsNotNone(source_row)

            listing_row = conn.execute(
                "SELECT source_id, source_listing_id, source_url FROM source_listings WHERE source_id = ? AND source_listing_id = ?",
                (source_row[0], "listing-123"),
            ).fetchone()
            self.assertIsNotNone(listing_row)
            self.assertEqual(listing_row[2], snapshot.source_url)

            snapshot_row = conn.execute(
                "SELECT id, source_id, source_listing_id, snapshot_hash, field_provenance FROM source_snapshots WHERE source_id = ? AND source_listing_id = ?",
                (source_row[0], "listing-123"),
            ).fetchone()
            self.assertIsNotNone(snapshot_row)
            self.assertIn("autoscout24", snapshot_row[4])

            provenance_row = conn.execute(
                "SELECT source_name, source_listing_id, field_provenance FROM source_provenance WHERE source_snapshot_id = ?",
                (snapshot_row[0],),
            ).fetchone()
            self.assertIsNotNone(provenance_row)
            self.assertEqual(provenance_row[0], "autoscout24")
            self.assertEqual(provenance_row[1], "listing-123")
        finally:
            conn.close()

    def test_canonical_snapshot_persistence_is_idempotent_per_source_listing(self):
        db_path = os.path.join(self.tempdir.name, "canonical-idempotent.db")
        config.DATABASE = db_path
        database.get_connection().close()

        snapshot = SourceSnapshot(
            source_name="mobile_de",
            source_listing_id="mobile-42",
            source_url="https://www.mobile.de/auto-inserat/mobile-42",
            discovered_at=datetime.now(),
            fetched_at=datetime.now(),
            raw_summary_payload={"mobileAdId": "mobile-42", "price": {"consumerPriceGross": 30000}},
            raw_detail_payload={"plainTextDescription": "Nice"},
            extracted_fields={"fingerprint": "fp-mobile-42", "price": 30000},
            field_provenance={"price": {"source_name": "mobile_de", "source_listing_id": "mobile-42", "field": "price.consumerPriceGross"}},
        )

        first = database.save_source_snapshot(snapshot)
        second = database.save_source_snapshot(snapshot)
        self.assertIsNotNone(first)
        self.assertEqual(first, second)

        conn = database.get_connection()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM source_snapshots WHERE source_listing_id = ?",
                ("mobile-42",),
            ).fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            conn.close()

    def test_canonical_snapshot_dry_run_does_not_persist_records(self):
        db_path = os.path.join(self.tempdir.name, "canonical-dry-run.db")
        config.DATABASE = db_path
        database.get_connection().close()

        snapshot = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="listing-999",
            source_url="https://www.autoscout24.de/angebote/listing-999",
            discovered_at=datetime.now(),
            fetched_at=datetime.now(),
            raw_summary_payload={"id": "listing-999"},
            raw_detail_payload={"description": "dry"},
            extracted_fields={"fingerprint": "fp-999", "price": 15000},
            field_provenance={"price": {"source_name": "autoscout24", "source_listing_id": "listing-999"}},
        )

        self.assertIsNone(database.save_source_snapshot(snapshot, dry_run=True))
        self.assertEqual(database.persist_source_snapshots([snapshot], dry_run=True), [])

        conn = database.get_connection()
        try:
            source_count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
            snapshot_count = conn.execute("SELECT COUNT(*) FROM source_snapshots").fetchone()[0]
            provenance_count = conn.execute("SELECT COUNT(*) FROM source_provenance").fetchone()[0]
            self.assertEqual(source_count, 0)
            self.assertEqual(snapshot_count, 0)
            self.assertEqual(provenance_count, 0)
        finally:
            conn.close()

    def test_same_semantic_snapshot_is_idempotent_across_timestamps(self):
        db_path = os.path.join(self.tempdir.name, "semantic-idempotent.db")
        config.DATABASE = db_path
        database.get_connection().close()

        first = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="listing-202",
            source_url="https://www.autoscout24.de/angebote/listing-202",
            discovered_at=datetime(2025, 1, 1, 12, 0, 0),
            fetched_at=datetime(2025, 1, 1, 12, 1, 0),
            raw_summary_payload={"id": "listing-202", "price": 25000},
            raw_detail_payload={"description": "Same description"},
            extracted_fields={"fingerprint": "fp-202", "price": 25000, "description": "Same description"},
            field_provenance={"price": {"source_name": "autoscout24", "source_listing_id": "listing-202"}},
        )
        second = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="listing-202",
            source_url="https://www.autoscout24.de/angebote/listing-202",
            discovered_at=datetime(2025, 1, 2, 12, 0, 0),
            fetched_at=datetime(2025, 1, 2, 12, 5, 0),
            raw_summary_payload={"id": "listing-202", "price": 25000},
            raw_detail_payload={"description": "Same description"},
            extracted_fields={"fingerprint": "fp-202", "price": 25000, "description": "Same description"},
            field_provenance={"price": {"source_name": "autoscout24", "source_listing_id": "listing-202"}},
        )

        persisted = database.persist_source_snapshots([first, second])
        self.assertEqual(len(persisted), 1)

        conn = database.get_connection()
        try:
            count = conn.execute("SELECT COUNT(*) FROM source_snapshots WHERE source_listing_id = ?", ("listing-202",)).fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            conn.close()

    def test_duplicate_snapshot_commits_listing_updates_when_connection_is_owned(self):
        db_path = os.path.join(self.tempdir.name, "duplicate-listing-update.db")
        config.DATABASE = db_path
        database.get_connection().close()

        initial = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="listing-duplicate-1",
            source_url="https://www.autoscout24.de/angebote/listing-duplicate-1-old",
            discovered_at=datetime(2025, 1, 1, 12, 0, 0),
            fetched_at=datetime(2025, 1, 1, 12, 1, 0),
            raw_summary_payload={"id": "listing-duplicate-1", "price": 17000},
            raw_detail_payload={"description": "Original"},
            extracted_fields={"fingerprint": "fp-duplicate-1", "price": 17000, "description": "Original"},
            field_provenance={"price": {"source_name": "autoscout24", "source_listing_id": "listing-duplicate-1"}},
        )
        duplicate = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="listing-duplicate-1",
            source_url="https://www.autoscout24.de/angebote/listing-duplicate-1-new",
            discovered_at=datetime(2025, 1, 2, 12, 0, 0),
            fetched_at=datetime(2025, 1, 2, 12, 5, 0),
            raw_summary_payload={"id": "listing-duplicate-1", "price": 17000},
            raw_detail_payload={"description": "Original"},
            extracted_fields={"fingerprint": "fp-duplicate-1", "price": 17000, "description": "Original"},
            field_provenance={"price": {"source_name": "autoscout24", "source_listing_id": "listing-duplicate-1"}},
        )

        first_id = database.save_source_snapshot(initial)
        second_id = database.save_source_snapshot(duplicate)

        self.assertEqual(first_id, second_id)
        self.assertEqual(first_id, 1)

        conn = database.get_connection()
        try:
            listing_row = conn.execute(
                "SELECT source_url, status FROM source_listings WHERE source_id = ? AND source_listing_id = ?",
                (1, "listing-duplicate-1"),
            ).fetchone()
            self.assertIsNotNone(listing_row)
            self.assertEqual(listing_row[0], "https://www.autoscout24.de/angebote/listing-duplicate-1-new")
            self.assertEqual(listing_row[1], "active")

            snapshot_count = conn.execute(
                "SELECT COUNT(*) FROM source_snapshots WHERE source_listing_id = ?",
                ("listing-duplicate-1",),
            ).fetchone()[0]
            self.assertEqual(snapshot_count, 1)
        finally:
            conn.close()

    def test_url_change_does_not_create_new_semantic_observation(self):
        db_path = os.path.join(self.tempdir.name, "semantic-url-idempotent.db")
        config.DATABASE = db_path
        database.get_connection().close()

        first = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="listing-777",
            source_url="https://www.autoscout24.de/angebote/listing-777-v1",
            discovered_at=datetime(2025, 1, 1, 12, 0, 0),
            fetched_at=datetime(2025, 1, 1, 12, 1, 0),
            raw_summary_payload={"id": "listing-777", "price": 18000},
            raw_detail_payload={"description": "Same description"},
            extracted_fields={"fingerprint": "fp-777", "price": 18000, "description": "Same description"},
            field_provenance={"price": {"source_name": "autoscout24", "source_listing_id": "listing-777"}},
        )
        second = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="listing-777",
            source_url="https://www.autoscout24.de/angebote/listing-777-v2",
            discovered_at=datetime(2025, 1, 2, 12, 0, 0),
            fetched_at=datetime(2025, 1, 2, 12, 5, 0),
            raw_summary_payload={"id": "listing-777", "price": 18000},
            raw_detail_payload={"description": "Same description"},
            extracted_fields={"fingerprint": "fp-777", "price": 18000, "description": "Same description"},
            field_provenance={"price": {"source_name": "autoscout24", "source_listing_id": "listing-777"}},
        )

        persisted = database.persist_source_snapshots([first, second])
        self.assertEqual(len(persisted), 1)

        conn = database.get_connection()
        try:
            count = conn.execute("SELECT COUNT(*) FROM source_snapshots WHERE source_listing_id = ?", ("listing-777",)).fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            conn.close()

    def test_same_vin_across_sources_resolves_to_one_vehicle(self):
        db_path = os.path.join(self.tempdir.name, "canonical-vehicle-vin.db")
        config.DATABASE = db_path
        database.get_connection().close()

        autoscout = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="as-100",
            source_url="https://www.autoscout24.de/angebote/as-100",
            discovered_at=datetime(2025, 1, 1),
            fetched_at=datetime(2025, 1, 1, 1, 0),
            raw_summary_payload={"id": "as-100", "vin": "WAU1234567890"},
            raw_detail_payload={"description": "Audi A5"},
            extracted_fields={"vin": "WAU1234567890", "make": "Audi", "model": "A5", "year": 2023, "body_type": "cabriolet"},
            field_provenance={"vin": {"source_name": "autoscout24", "source_listing_id": "as-100"}},
        )
        mobile = SourceSnapshot(
            source_name="mobile_de",
            source_listing_id="mob-500",
            source_url="https://www.mobile.de/auto-inserat/mob-500",
            discovered_at=datetime(2025, 1, 2),
            fetched_at=datetime(2025, 1, 2, 1, 0),
            raw_summary_payload={"mobileAdId": "mob-500", "vin": "WAU1234567890"},
            raw_detail_payload={"description": "Same car"},
            extracted_fields={"vin": "WAU1234567890", "make": "Audi", "model": "A5", "year": 2023, "body_type": "cabriolet"},
            field_provenance={"vin": {"source_name": "mobile_de", "source_listing_id": "mob-500"}},
        )

        database.persist_source_snapshots([autoscout, mobile])
        result = database.resolve_canonical_vehicle_links([autoscout, mobile])
        self.assertEqual(len(result), 2)

        conn = database.get_connection()
        try:
            vehicle_count = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
            listing_count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            linked_vehicle_ids = {
                row[0] for row in conn.execute("SELECT vehicle_id FROM listings").fetchall()
                if row[0] is not None
            }
            self.assertEqual(vehicle_count, 1)
            self.assertEqual(listing_count, 2)
            self.assertEqual(len(linked_vehicle_ids), 1)
        finally:
            conn.close()

    def test_linked_vehicle_same_vin_keeps_existing_vehicle(self):
        db_path = os.path.join(self.tempdir.name, "canonical-linked-same-vin.db")
        config.DATABASE = db_path
        database.get_connection().close()

        snapshot = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="as-410",
            source_url="https://www.autoscout24.de/angebote/as-410",
            discovered_at=datetime(2025, 1, 1),
            fetched_at=datetime(2025, 1, 1, 1, 0),
            raw_summary_payload={"id": "as-410", "vin": "WAU1111111111"},
            raw_detail_payload={"description": "Audi A5"},
            extracted_fields={"vin": "WAU1111111111", "make": "Audi", "model": "A5", "year": 2023},
            field_provenance={"vin": {"source_name": "autoscout24", "source_listing_id": "as-410"}},
        )
        database.save_source_snapshot(snapshot)

        conn = database.get_connection()
        try:
            source_row = conn.execute("SELECT id FROM sources WHERE source_name = ?", ("autoscout24",)).fetchone()
            source_listing_row = conn.execute(
                "SELECT id FROM source_listings WHERE source_id = ? AND source_listing_id = ?",
                (source_row[0], "as-410"),
            ).fetchone()
            conn.execute(
                "INSERT INTO vehicles (vin, make, model, status) VALUES (?, 'Audi', 'A5', 'active')",
                ("WAU1111111111",),
            )
            vehicle_id = conn.execute("SELECT id FROM vehicles WHERE vin = ?", ("WAU1111111111",)).fetchone()[0]
            listing_id = conn.execute("SELECT id FROM listings WHERE source_listing_row_id = ?", (source_listing_row[0],)).fetchone()[0]
            conn.execute(
                "UPDATE listings SET vehicle_id = ?, status = 'linked' WHERE id = ?",
                (vehicle_id, listing_id),
            )

            outcome_listing_id, outcome_vehicle_id, outcome = database.resolve_canonical_listing_and_vehicle(snapshot, conn=conn)
            provenance = conn.execute(
                "SELECT outcome, review_required FROM listing_vehicle_mappings WHERE listing_id = ? ORDER BY id DESC LIMIT 1",
                (listing_id,),
            ).fetchone()
            self.assertEqual(outcome_listing_id, listing_id)
            self.assertEqual(outcome_vehicle_id, vehicle_id)
            self.assertEqual(outcome, "EXISTING_LISTING")
            self.assertEqual(provenance[0], "EXISTING_LISTING")
            self.assertEqual(provenance[1], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM vehicles WHERE vin = ?", ("WAU1111111111",)).fetchone()[0], 1)
        finally:
            conn.close()

    def test_linked_vehicle_conflicting_vin_requires_operator_review(self):
        db_path = os.path.join(self.tempdir.name, "canonical-linked-conflict.db")
        config.DATABASE = db_path
        database.get_connection().close()

        snapshot = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="as-420",
            source_url="https://www.autoscout24.de/angebote/as-420",
            discovered_at=datetime(2025, 1, 1),
            fetched_at=datetime(2025, 1, 1, 1, 0),
            raw_summary_payload={"id": "as-420", "vin": "WAU2222222222"},
            raw_detail_payload={"description": "Audi A5"},
            extracted_fields={"vin": "WAU2222222222", "make": "Audi", "model": "A5", "year": 2023},
            field_provenance={"vin": {"source_name": "autoscout24", "source_listing_id": "as-420"}},
        )
        database.save_source_snapshot(snapshot)

        conn = database.get_connection()
        try:
            source_row = conn.execute("SELECT id FROM sources WHERE source_name = ?", ("autoscout24",)).fetchone()
            source_listing_row = conn.execute(
                "SELECT id FROM source_listings WHERE source_id = ? AND source_listing_id = ?",
                (source_row[0], "as-420"),
            ).fetchone()
            conn.execute("INSERT INTO vehicles (vin, make, model, status) VALUES (?, 'Audi', 'A5', 'active')", ("WAU1111111111",))
            vehicle_a = conn.execute("SELECT id FROM vehicles WHERE vin = ?", ("WAU1111111111",)).fetchone()[0]
            conn.execute("INSERT INTO vehicles (vin, make, model, status) VALUES (?, 'Audi', 'A5', 'active')", ("WAU2222222222",))
            vehicle_b = conn.execute("SELECT id FROM vehicles WHERE vin = ?", ("WAU2222222222",)).fetchone()[0]
            listing_id = conn.execute("SELECT id FROM listings WHERE source_listing_row_id = ?", (source_listing_row[0],)).fetchone()[0]
            conn.execute(
                "UPDATE listings SET vehicle_id = ?, status = 'linked' WHERE id = ?",
                (vehicle_a, listing_id),
            )

            outcome_listing_id, outcome_vehicle_id, outcome = database.resolve_canonical_listing_and_vehicle(snapshot, conn=conn)
            provenance = conn.execute(
                "SELECT outcome, review_required, evidence FROM listing_vehicle_mappings WHERE listing_id = ? ORDER BY id DESC LIMIT 1",
                (listing_id,),
            ).fetchone()
            self.assertEqual(outcome_listing_id, listing_id)
            self.assertEqual(outcome_vehicle_id, vehicle_a)
            self.assertEqual(outcome, "OPERATOR_REVIEW")
            self.assertEqual(provenance[0], "OPERATOR_REVIEW")
            self.assertEqual(provenance[1], 1)
            self.assertIn("authoritative_vin_conflict", provenance[2])
            self.assertEqual(conn.execute("SELECT vehicle_id FROM listings WHERE id = ?", (listing_id,)).fetchone()[0], vehicle_a)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM vehicles WHERE vin = ?", ("WAU2222222222",)).fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM vehicles WHERE id IN (?, ?)", (vehicle_a, vehicle_b)).fetchone()[0], 2)
        finally:
            conn.close()

    def test_existing_vehicle_without_vin_can_be_enriched_by_later_vin(self):
        db_path = os.path.join(self.tempdir.name, "canonical-null-vin-enrich.db")
        config.DATABASE = db_path
        database.get_connection().close()

        snapshot = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="as-430",
            source_url="https://www.autoscout24.de/angebote/as-430",
            discovered_at=datetime(2025, 1, 1),
            fetched_at=datetime(2025, 1, 1, 1, 0),
            raw_summary_payload={"id": "as-430", "vin": "WAU3333333333"},
            raw_detail_payload={"description": "Audi A5"},
            extracted_fields={"vin": "WAU3333333333", "make": "Audi", "model": "A5", "year": 2023},
            field_provenance={"vin": {"source_name": "autoscout24", "source_listing_id": "as-430"}},
        )
        database.save_source_snapshot(snapshot)

        conn = database.get_connection()
        try:
            source_row = conn.execute("SELECT id FROM sources WHERE source_name = ?", ("autoscout24",)).fetchone()
            source_listing_row = conn.execute(
                "SELECT id FROM source_listings WHERE source_id = ? AND source_listing_id = ?",
                (source_row[0], "as-430"),
            ).fetchone()
            conn.execute("INSERT INTO vehicles (vin, make, model, status) VALUES (NULL, 'Audi', 'A5', 'active')")
            vehicle_id = conn.execute("SELECT id FROM vehicles WHERE vin IS NULL ORDER BY id DESC LIMIT 1").fetchone()[0]
            listing_id = conn.execute("SELECT id FROM listings WHERE source_listing_row_id = ?", (source_listing_row[0],)).fetchone()[0]
            conn.execute(
                "UPDATE listings SET vehicle_id = ?, status = 'linked' WHERE id = ?",
                (vehicle_id, listing_id),
            )

            outcome_listing_id, outcome_vehicle_id, outcome = database.resolve_canonical_listing_and_vehicle(snapshot, conn=conn)
            provenance = conn.execute(
                "SELECT outcome, review_required FROM listing_vehicle_mappings WHERE listing_id = ? ORDER BY id DESC LIMIT 1",
                (listing_id,),
            ).fetchone()
            self.assertEqual(outcome_listing_id, listing_id)
            self.assertEqual(outcome_vehicle_id, vehicle_id)
            self.assertEqual(outcome, "MATCHED_EXISTING_VEHICLE")
            self.assertEqual(provenance[0], "MATCHED_EXISTING_VEHICLE")
            self.assertEqual(provenance[1], 0)
            self.assertEqual(conn.execute("SELECT vin FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()[0], "WAU3333333333")
        finally:
            conn.close()

    def test_no_vin_does_not_auto_merge_vehicle_identity(self):
        db_path = os.path.join(self.tempdir.name, "canonical-no-vin.db")
        config.DATABASE = db_path
        database.get_connection().close()

        first = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="as-200",
            source_url="https://www.autoscout24.de/angebote/as-200",
            discovered_at=datetime(2025, 1, 1),
            fetched_at=datetime(2025, 1, 1, 1, 0),
            raw_summary_payload={"id": "as-200"},
            raw_detail_payload={"description": "Audi A5"},
            extracted_fields={"make": "Audi", "model": "A5", "year": 2023, "body_type": "cabriolet"},
            field_provenance={"make": {"source_name": "autoscout24", "source_listing_id": "as-200"}},
        )
        second = SourceSnapshot(
            source_name="mobile_de",
            source_listing_id="mob-600",
            source_url="https://www.mobile.de/auto-inserat/mob-600",
            discovered_at=datetime(2025, 1, 2),
            fetched_at=datetime(2025, 1, 2, 1, 0),
            raw_summary_payload={"mobileAdId": "mob-600"},
            raw_detail_payload={"description": "Audi A5"},
            extracted_fields={"make": "Audi", "model": "A5", "year": 2023, "body_type": "cabriolet"},
            field_provenance={"model": {"source_name": "mobile_de", "source_listing_id": "mob-600"}},
        )

        database.persist_source_snapshots([first, second])
        database.resolve_canonical_vehicle_links([first, second])

        conn = database.get_connection()
        try:
            vehicle_count = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
            listing_rows = conn.execute("SELECT vehicle_id, status FROM listings ORDER BY id").fetchall()
            self.assertEqual(vehicle_count, 0)
            self.assertEqual(len(listing_rows), 2)
            self.assertTrue(all(row[0] is None for row in listing_rows))
            self.assertTrue(all(row[1] == "unresolved" for row in listing_rows))
        finally:
            conn.close()

    def test_later_vin_resolves_existing_unresolved_listing(self):
        db_path = os.path.join(self.tempdir.name, "canonical-later-vin.db")
        config.DATABASE = db_path
        database.get_connection().close()

        unresolved = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="as-300",
            source_url="https://www.autoscout24.de/angebote/as-300",
            discovered_at=datetime(2025, 1, 1),
            fetched_at=datetime(2025, 1, 1, 1, 0),
            raw_summary_payload={"id": "as-300"},
            raw_detail_payload={"description": "Audi A5"},
            extracted_fields={"make": "Audi", "model": "A5", "year": 2023, "body_type": "cabriolet"},
            field_provenance={"make": {"source_name": "autoscout24", "source_listing_id": "as-300"}},
        )

        database.persist_source_snapshots([unresolved])
        database.resolve_canonical_vehicle_links([unresolved])

        resolved = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="as-300",
            source_url="https://www.autoscout24.de/angebote/as-300",
            discovered_at=datetime(2025, 1, 2),
            fetched_at=datetime(2025, 1, 2, 1, 0),
            raw_summary_payload={"id": "as-300", "vin": "WAU9876543210"},
            raw_detail_payload={"description": "Audi A5 with VIN"},
            extracted_fields={"vin": "WAU9876543210", "make": "Audi", "model": "A5", "year": 2023},
            field_provenance={"vin": {"source_name": "autoscout24", "source_listing_id": "as-300"}},
        )

        database.resolve_canonical_vehicle_links([resolved])

        conn = database.get_connection()
        try:
            vehicle_count = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
            linked_listing = conn.execute("SELECT vehicle_id, status FROM listings WHERE source_listing_id = ?", ("as-300",)).fetchone()
            self.assertEqual(vehicle_count, 1)
            self.assertIsNotNone(linked_listing[0])
            self.assertEqual(linked_listing[1], "linked")
        finally:
            conn.close()

    def test_semantic_change_creates_new_observation(self):
        db_path = os.path.join(self.tempdir.name, "semantic-change.db")
        config.DATABASE = db_path
        database.get_connection().close()

        original = SourceSnapshot(
            source_name="mobile_de",
            source_listing_id="mobile-333",
            source_url="https://www.mobile.de/auto-inserat/mobile-333",
            discovered_at=datetime(2025, 1, 1),
            fetched_at=datetime(2025, 1, 1, 1, 0),
            raw_summary_payload={"mobileAdId": "mobile-333", "price": {"consumerPriceGross": 25000}},
            raw_detail_payload={"description": "Old"},
            extracted_fields={"price": 25000, "description": "Old"},
            field_provenance={"price": {"source_name": "mobile_de", "source_listing_id": "mobile-333"}},
        )
        changed = SourceSnapshot(
            source_name="mobile_de",
            source_listing_id="mobile-333",
            source_url="https://www.mobile.de/auto-inserat/mobile-333",
            discovered_at=datetime(2025, 1, 2),
            fetched_at=datetime(2025, 1, 2, 1, 0),
            raw_summary_payload={"mobileAdId": "mobile-333", "price": {"consumerPriceGross": 26000}},
            raw_detail_payload={"description": "New"},
            extracted_fields={"price": 26000, "description": "New"},
            field_provenance={"price": {"source_name": "mobile_de", "source_listing_id": "mobile-333"}},
        )

        persisted = database.persist_source_snapshots([original, changed])
        self.assertEqual(len(persisted), 2)

        conn = database.get_connection()
        try:
            count = conn.execute("SELECT COUNT(*) FROM source_snapshots WHERE source_listing_id = ?", ("mobile-333",)).fetchone()[0]
            self.assertEqual(count, 2)
        finally:
            conn.close()

    def test_batch_persistence_rolls_back_on_failure(self):
        db_path = os.path.join(self.tempdir.name, "batch-atomic.db")
        config.DATABASE = db_path
        database.get_connection().close()

        first = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="batch-1",
            source_url="https://www.autoscout24.de/angebote/batch-1",
            discovered_at=datetime.now(),
            fetched_at=datetime.now(),
            raw_summary_payload={"id": "batch-1"},
            raw_detail_payload={"description": "ok"},
            extracted_fields={"fingerprint": "fp-batch-1", "price": 20000},
            field_provenance={"price": {"source_name": "autoscout24", "source_listing_id": "batch-1"}},
        )
        second = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="batch-2",
            source_url="https://www.autoscout24.de/angebote/batch-2",
            discovered_at=datetime.now(),
            fetched_at=datetime.now(),
            raw_summary_payload={"id": "batch-2"},
            raw_detail_payload={"description": "fail"},
            extracted_fields={"fingerprint": "fp-batch-2", "price": 30000},
            field_provenance={"price": {"source_name": "autoscout24", "source_listing_id": "batch-2"}},
        )

        original_json = database._canonical_json

        def fake_json(value):
            if value and isinstance(value, dict) and value.get("source_listing_id") == "batch-2":
                raise TypeError("simulated batch failure")
            return original_json(value)

        try:
            with mock.patch("database._canonical_json", side_effect=fake_json):
                with self.assertRaises(TypeError):
                    database.persist_source_snapshots([first, second])
        finally:
            pass

        conn = database.get_connection()
        try:
            count = conn.execute("SELECT COUNT(*) FROM source_snapshots").fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            conn.close()

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


# ============================================================================
# ARCH-010: MOBILE.DE SEARCH API TESTS
# ============================================================================

class TestMobileDeAPIClient:
    """Test Mobile.de API client."""

    def test_client_creation_with_credentials(self):
        """Test API client instantiation with credentials."""
        from sources.mobile_de import MobileDeAPIClient

        client = MobileDeAPIClient(username="test_user", password="test_pass")
        assert client.username == "test_user"
        assert client.password == "test_pass"
        assert client.credentials_available()

    def test_client_creation_without_credentials(self):
        """Test API client without credentials."""
        from sources.mobile_de import MobileDeAPIClient
        import os

        # Ensure environment variables are not set
        os.environ.pop("MOBILE_DE_API_USERNAME", None)
        os.environ.pop("MOBILE_DE_API_PASSWORD", None)

        client = MobileDeAPIClient()
        assert not client.credentials_available()

    def test_client_auth_header_building(self):
        """Test HTTP Basic Auth header construction."""
        from sources.mobile_de import MobileDeAPIClient
        import base64

        client = MobileDeAPIClient(username="user", password="pass")
        auth_header = client._build_auth_header()

        # Should be "Basic <base64-encoded-user:pass>"
        assert auth_header.startswith("Basic ")
        encoded_part = auth_header.split(" ")[1]
        decoded = base64.b64decode(encoded_part).decode()
        assert decoded == "user:pass"


class TestMobileDeAdapter:
    """Test Mobile.de source adapter."""

    def test_adapter_creation(self):
        """Test adapter instantiation."""
        from sources.mobile_de import MobileDeSourceAdapter, MobileDeAPIClient

        client = MobileDeAPIClient(username="test", password="test")
        adapter = MobileDeSourceAdapter(api_client=client, max_pages=5)
        assert adapter.api_client == client
        assert adapter.max_pages == 5

    def test_adapter_descriptor(self):
        """Test adapter descriptor."""
        from sources.mobile_de import MobileDeSourceAdapter

        adapter = MobileDeSourceAdapter()
        descriptor = adapter.descriptor()

        assert descriptor.source_name == "mobile_de"
        assert descriptor.display_name == "Mobile.de"
        assert descriptor.base_url == "https://www.mobile.de"
        assert descriptor.plugin_descriptor.plugin_id == "mobile_de"

    def test_adapter_capabilities(self):
        """Test adapter capabilities."""
        from sources.mobile_de import MobileDeSourceAdapter

        adapter = MobileDeSourceAdapter()
        capabilities = adapter.capabilities()

        assert capabilities.supports_listing_discovery
        assert capabilities.supports_detail_fetch
        assert capabilities.supports_description_fetch
        assert capabilities.supports_full_inventory_scan

    def test_parse_ad_listing_valid(self):
        """Test parsing a valid ad listing."""
        from sources.mobile_de import MobileDeSourceAdapter
        from sources.base import SourceContext
        from datetime import datetime

        adapter = MobileDeSourceAdapter()
        context = SourceContext(source_name="mobile_de")
        discovered_at = datetime.now()

        # Official Mobile.de API response example
        ad = {
            "mobileAdId": "15012",
            "detailPageUrl": "https://suchen.mobile.de/auto-inserat/abarth-500-w-stheuterode/15012.html",
            "make": "ABARTH",
            "model": "500",
            "modelDescription": "500 TwinAir",
            "condition": "USED",
            "firstRegistration": "202007",
            "mileage": 500,
            "fuel": "DIESEL",
            "category": "EstateCar",
            "price": {
                "consumerPriceGross": "1000.00",
                "currency": "EUR",
                "type": "FIXED"
            },
            "seller": {
                "mobileSellerId": "11",
                "type": "DEALER",
                "commercial": True,
                "companyName": "Test Dealer",
                "email": "test@dealer.de",
                "address": {
                    "city": "Berlin",
                    "zipcode": "10115",
                    "country": "DE"
                },
                "geoData": {
                    "lat": 52.5200,
                    "lon": 13.4050
                }
            },
            "plainTextDescription": "Well-maintained vehicle"
        }

        listing = adapter._parse_ad_listing(ad, discovered_at, context)
        assert listing is not None
        assert listing.source_listing_id == "15012"
        assert listing.source_name == "mobile_de"
        assert "15012" in listing.source_url

    def test_parse_ad_listing_missing_id(self):
        """Test parsing ad without mobile_ad_id returns None."""
        from sources.mobile_de import MobileDeSourceAdapter
        from sources.base import SourceContext
        from datetime import datetime

        adapter = MobileDeSourceAdapter()
        context = SourceContext(source_name="mobile_de")
        discovered_at = datetime.now()

        ad = {
            "make": "BMW",
            "model": "3 Series",
            # Missing mobileAdId
        }

        listing = adapter._parse_ad_listing(ad, discovered_at, context)
        assert listing is None

    def test_extract_fields_complete(self):
        """Test field extraction from complete ad."""
        from sources.mobile_de import MobileDeSourceAdapter

        adapter = MobileDeSourceAdapter()

        ad = {
            "make": "BMW",
            "model": "3 Series",
            "modelDescription": "320d xDrive",
            "condition": "USED",
            "firstRegistration": "201803",
            "mileage": 125000,
            "fuel": "DIESEL",
            "category": "Sedan",
            "price": {
                "consumerPriceGross": "25500.00",
                "currency": "EUR"
            },
            "damageUnrepaired": False,
            "seller": {
                "type": "DEALER",
                "commercial": True,
                "companyName": "BMW Dealer",
                "email": "info@bmwdealer.de",
                "address": {
                    "city": "Munich",
                    "zipcode": "80331",
                    "country": "DE"
                },
                "geoData": {
                    "lat": 48.1351,
                    "lon": 11.5820
                }
            },
            "plainTextDescription": "Excellent condition"
        }

        extracted = adapter._extract_fields(ad)

        assert extracted["make"] == "BMW"
        assert extracted["model"] == "3 Series"
        assert extracted["model_variant"] == "320d xDrive"
        assert extracted["year"] == 2018
        assert extracted["mileage"] == 125000
        assert extracted["fuel"] == "DIESEL"
        assert extracted["body_type"] == "Sedan"
        assert extracted["price_gross"] == 25500.00
        assert extracted["currency"] == "EUR"
        assert extracted["seller_name"] == "BMW Dealer"
        assert extracted["location_city"] == "Munich"
        assert extracted["description"] == "Excellent condition"

    def test_extract_fields_partial(self):
        """Test field extraction with missing optional fields."""
        from sources.mobile_de import MobileDeSourceAdapter

        adapter = MobileDeSourceAdapter()

        ad = {
            "make": "Audi",
            "model": "A4",
            "mileage": 75000,
            # Missing: modelDescription, year, price details, seller, etc.
        }

        extracted = adapter._extract_fields(ad)

        # Should include present fields
        assert extracted["make"] == "Audi"
        assert extracted["model"] == "A4"
        assert extracted["mileage"] == 75000

        # Should NOT fabricate missing fields
        assert "model_variant" not in extracted
        assert "price_gross" not in extracted
        assert "seller_name" not in extracted

    def test_extract_fields_with_description(self):
        """Test field extraction with explicit description."""
        from sources.mobile_de import MobileDeSourceAdapter

        adapter = MobileDeSourceAdapter()
        ad = {"make": "BMW"}
        custom_description = "Custom description text"

        extracted = adapter._extract_fields(ad, description=custom_description)
        assert extracted["description"] == custom_description

    def test_extract_fields_no_description(self):
        """Test field extraction falls back to plainTextDescription."""
        from sources.mobile_de import MobileDeSourceAdapter

        adapter = MobileDeSourceAdapter()
        ad = {
            "make": "BMW",
            "plainTextDescription": "From API response"
        }

        extracted = adapter._extract_fields(ad, description=None)
        assert extracted["description"] == "From API response"


class TestMobileDeConfiguration:
    """Test Mobile.de configuration and registration."""

    def test_mobile_de_in_registry(self):
        """Test Mobile.de is in source registry config."""
        import config

        assert "mobile_de" in config.SOURCE_REGISTRY
        assert config.SOURCE_REGISTRY["mobile_de"]["enabled"] is True

    def test_mobile_de_instance_configured(self):
        """Test Mobile.de instance is configured."""
        import config

        assert "mobile_de_primary" in config.SOURCE_INSTANCES
        instance_config = config.SOURCE_INSTANCES["mobile_de_primary"]
        assert instance_config["source_family"] == "mobile_de"
        assert instance_config["plugin_id"] == "mobile_de"
        assert instance_config["enabled"] is True

    def test_mobile_de_registration(self):
        """Test Mobile.de adapter registers correctly."""
        from sources import build_default_source_registry

        registry = build_default_source_registry()
        adapter = registry.get("mobile_de")
        assert adapter is not None
        from sources.mobile_de import MobileDeSourceAdapter
        assert isinstance(adapter, MobileDeSourceAdapter)

    def test_mobile_de_instance_creation(self):
        """Test Mobile.de source instance is created."""
        from sources import build_default_source_registry, build_source_instances

        registry = build_default_source_registry()
        instances = build_source_instances(registry)

        mobile_de_instances = [i for i in instances if i.source_family == "mobile_de"]
        assert len(mobile_de_instances) > 0
        assert mobile_de_instances[0].instance_id == "mobile_de_primary"


class TestMobileDeIntegration:
    """Integration tests for Mobile.de with coordinator."""

    def test_mobile_de_and_autoscout24_both_available(self):
        """Test both AutoScout24 and Mobile.de are available."""
        from sources import build_default_source_registry

        registry = build_default_source_registry()
        autoscout24_adapter = registry.get("autoscout24")
        mobile_de_adapter = registry.get("mobile_de")

        assert autoscout24_adapter is not None
        assert mobile_de_adapter is not None

    def test_mobile_de_descriptor_distinct(self):
        """Test Mobile.de descriptor is distinct from AutoScout24."""
        from sources.mobile_de import MobileDeSourceAdapter
        from sources.autoscout24 import AutoScout24SourceAdapter

        mobile_de = MobileDeSourceAdapter()
        autoscout24 = AutoScout24SourceAdapter()

        assert mobile_de.descriptor().source_name != autoscout24.descriptor().source_name
        assert "mobile_de" in mobile_de.descriptor().plugin_descriptor.plugin_id


class TestCanonicalListingCurrentState(unittest.TestCase):
    def setUp(self):
        self.original_database = config.DATABASE
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        config.DATABASE = self.original_database
        self.tempdir.cleanup()

    def _snapshot(self, source_name, listing_id, *, price=45000, mileage=18000, description="Audi A5", url=None, vin=None, discovered_at=None, fetched_at=None):
        payload = {
            "source_name": source_name,
            "source_listing_id": listing_id,
            "source_url": url or f"https://example.com/{listing_id}",
            "discovered_at": discovered_at or datetime(2025, 1, 1, 12, 0, 0),
            "fetched_at": fetched_at or datetime(2025, 1, 1, 12, 5, 0),
            "raw_summary_payload": {"id": listing_id, "price": price, "mileage": mileage, "url": url or f"https://example.com/{listing_id}"},
            "raw_detail_payload": {"description": description, "seller": "Dealer One"},
            "extracted_fields": {
                "fingerprint": f"fp-{listing_id}",
                "price": price,
                "mileage": mileage,
                "description": description,
                "seller": "Dealer One",
                "vin": vin,
            },
            "field_provenance": {
                "price": {"source_name": source_name},
                "mileage": {"source_name": source_name},
                "description": {"source_name": source_name},
            },
        }
        return SourceSnapshot(**payload)

    def test_listing_current_state_created_from_first_snapshot(self):
        db_path = os.path.join(self.tempdir.name, "listing-current-state.db")
        config.DATABASE = db_path
        database.get_connection().close()

        snapshot = self._snapshot("autoscout24", "listing-1", price=44500, mileage=18400)
        row_id = database.save_source_snapshot(snapshot)
        self.assertIsNotNone(row_id)

        conn = database.get_connection()
        try:
            listing_row = conn.execute(
                "SELECT current_price, current_mileage, current_description, current_url, availability FROM listings WHERE source_listing_id = ?",
                ("listing-1",),
            ).fetchone()
            self.assertIsNotNone(listing_row)
            self.assertEqual(listing_row[0], 44500)
            self.assertEqual(listing_row[1], 18400)
            self.assertIn("Audi A5", listing_row[2])
            self.assertEqual(listing_row[4], "ACTIVE")
        finally:
            conn.close()

    def test_mobile_de_price_gross_sets_listing_current_price(self):
        db_path = os.path.join(self.tempdir.name, "listing-price-gross.db")
        config.DATABASE = db_path
        database.get_connection().close()

        snapshot = SourceSnapshot(
            source_name="mobile_de",
            source_listing_id="mobile-price-1",
            source_url="https://www.mobile.de/auto-inserat/mobile-price-1",
            discovered_at=datetime(2025, 3, 1, 10, 0, 0),
            fetched_at=datetime(2025, 3, 1, 10, 5, 0),
            raw_summary_payload={
                "mobileAdId": "mobile-price-1",
                "price": {"consumerPriceGross": 25500},
            },
            raw_detail_payload={"description": "Nice Audi"},
            extracted_fields={
                "fingerprint": "fp-mobile-price-1",
                "price_gross": 25500,
                "description": "Nice Audi",
            },
            field_provenance={"price_gross": {"source_name": "mobile_de"}},
        )

        snapshot_id = database.save_source_snapshot(snapshot)
        self.assertIsNotNone(snapshot_id)

        conn = database.get_connection()
        try:
            listing_row = conn.execute(
                "SELECT current_price, current_mileage, availability FROM listings WHERE source_listing_id = ?",
                ("mobile-price-1",),
            ).fetchone()
            self.assertEqual(listing_row[0], 25500)
            self.assertIsNone(listing_row[1])
            self.assertEqual(listing_row[2], "ACTIVE")
        finally:
            conn.close()

    def test_status_change_creates_new_semantic_observation_and_updates_availability(self):
        db_path = os.path.join(self.tempdir.name, "listing-status-change.db")
        config.DATABASE = db_path
        database.get_connection().close()

        active = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="listing-status-1",
            source_url="https://example.com/listing-status-1",
            discovered_at=datetime(2025, 4, 1, 9, 0, 0),
            fetched_at=datetime(2025, 4, 1, 9, 5, 0),
            raw_summary_payload={"id": "listing-status-1", "status": "active"},
            raw_detail_payload={"description": "Active listing"},
            extracted_fields={"fingerprint": "fp-listing-status-1", "price": 20000, "status": "active"},
            field_provenance={"status": {"source_name": "autoscout24"}},
        )
        sold = SourceSnapshot(
            source_name="autoscout24",
            source_listing_id="listing-status-1",
            source_url="https://example.com/listing-status-1",
            discovered_at=datetime(2025, 4, 2, 9, 0, 0),
            fetched_at=datetime(2025, 4, 2, 9, 5, 0),
            raw_summary_payload={"id": "listing-status-1", "status": "sold"},
            raw_detail_payload={"description": "Sold listing"},
            extracted_fields={"fingerprint": "fp-listing-status-1", "price": 20000, "status": "sold"},
            field_provenance={"status": {"source_name": "autoscout24"}},
        )

        first_id = database.save_source_snapshot(active)
        second_id = database.save_source_snapshot(sold)
        self.assertNotEqual(first_id, second_id)

        conn = database.get_connection()
        try:
            snapshot_count = conn.execute(
                "SELECT COUNT(*) FROM source_snapshots WHERE source_listing_id = ?",
                ("listing-status-1",),
            ).fetchone()[0]
            listing_row = conn.execute(
                "SELECT availability, latest_source_snapshot_id FROM listings WHERE source_listing_id = ?",
                ("listing-status-1",),
            ).fetchone()
            self.assertEqual(snapshot_count, 2)
            self.assertEqual(listing_row[0], "SOLD")
            self.assertEqual(listing_row[1], second_id)
        finally:
            conn.close()

    def test_boolean_availability_values_are_respected(self):
        db_path = os.path.join(self.tempdir.name, "listing-boolean-availability.db")
        config.DATABASE = db_path
        database.get_connection().close()

        for field_name, raw_value, expected in [
            ("is_available", True, "ACTIVE"),
            ("is_available", False, "INACTIVE"),
            ("available", False, "INACTIVE"),
            ("sold", True, "SOLD"),
            ("sold", False, "ACTIVE"),
        ]:
            snapshot = SourceSnapshot(
                source_name="autoscout24",
                source_listing_id=f"bool-{field_name}-{raw_value}",
                source_url=f"https://example.com/bool-{field_name}-{raw_value}",
                discovered_at=datetime(2025, 5, 1, 8, 0, 0),
                fetched_at=datetime(2025, 5, 1, 8, 5, 0),
                raw_summary_payload={field_name: raw_value},
                raw_detail_payload={"description": "bool test"},
                extracted_fields={"fingerprint": f"fp-{field_name}-{raw_value}", field_name: raw_value},
                field_provenance={field_name: {"source_name": "autoscout24"}},
            )
            database.save_source_snapshot(snapshot)
            conn = database.get_connection()
            try:
                row = conn.execute(
                    "SELECT availability FROM listings WHERE source_listing_id = ?",
                    (f"bool-{field_name}-{raw_value}",),
                ).fetchone()
                self.assertEqual(row[0], expected)
            finally:
                conn.close()

    def test_existing_listing_defaults_to_unknown(self):
        db_path = os.path.join(self.tempdir.name, "listing-default-unknown.db")
        config.DATABASE = db_path
        database.get_connection().close()

        conn = database.get_connection()
        try:
            conn.execute(
                "INSERT INTO sources (source_name, display_name, source_url, created_at) VALUES (?, ?, ?, datetime('now'))",
                ("autoscout24", "autoscout24", "https://example.com"),
            )
            source_id = conn.execute("SELECT id FROM sources WHERE source_name = ?", ("autoscout24",)).fetchone()[0]
            conn.execute(
                "INSERT INTO source_listings (source_id, source_listing_id, source_url, first_seen, last_seen, status) VALUES (?, ?, ?, datetime('now'), datetime('now'), 'active')",
                (source_id, "legacy-listing", "https://example.com/legacy-listing"),
            )
            source_listing_id = conn.execute(
                "SELECT id FROM source_listings WHERE source_id = ? AND source_listing_id = ?",
                (source_id, "legacy-listing"),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO listings (source_id, source_listing_id, source_listing_row_id, canonical_url, status) VALUES (?, ?, ?, '', 'active')",
                (source_id, "legacy-listing", source_listing_id),
            )
            row = conn.execute(
                "SELECT availability FROM listings WHERE source_listing_id = ?",
                ("legacy-listing",),
            ).fetchone()
            self.assertEqual(row[0], "UNKNOWN")
        finally:
            conn.close()

    def test_partial_newer_snapshot_keeps_previous_mileage_and_tracks_newer_snapshot(self):
        db_path = os.path.join(self.tempdir.name, "listing-partial-update.db")
        config.DATABASE = db_path
        database.get_connection().close()

        older = self._snapshot("autoscout24", "listing-partial", price=44500, mileage=18400, description="Older")
        newer = self._snapshot(
            "autoscout24",
            "listing-partial",
            price=43900,
            mileage=18400,
            description="Newer",
            discovered_at=datetime(2025, 2, 1, 12, 0, 0),
            fetched_at=datetime(2025, 2, 1, 12, 5, 0),
        )
        newer.extracted_fields.pop("mileage", None)
        newer.raw_summary_payload.pop("mileage", None)

        older_id = database.save_source_snapshot(older)
        newer_id = database.save_source_snapshot(newer)
        self.assertIsNotNone(older_id)
        self.assertIsNotNone(newer_id)
        self.assertNotEqual(older_id, newer_id)

        conn = database.get_connection()
        try:
            listing_row = conn.execute(
                "SELECT current_price, current_mileage, latest_source_snapshot_id FROM listings WHERE source_listing_id = ?",
                ("listing-partial",),
            ).fetchone()
            self.assertEqual(listing_row[0], 43900)
            self.assertEqual(listing_row[1], 18400)
            self.assertEqual(listing_row[2], newer_id)

            rows = conn.execute(
                "SELECT id, extracted_fields FROM source_snapshots WHERE source_listing_id = ? ORDER BY id",
                ("listing-partial",),
            ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertIn("18400", rows[0][1])
            self.assertIn("price", rows[1][1])
        finally:
            conn.close()

    def test_listing_price_and_mileage_update_uses_newer_snapshot(self):
        db_path = os.path.join(self.tempdir.name, "listing-update.db")
        config.DATABASE = db_path
        database.get_connection().close()

        older = self._snapshot("autoscout24", "listing-2", price=44500, mileage=18400, description="Older")
        newer = self._snapshot(
            "autoscout24",
            "listing-2",
            price=43900,
            mileage=17850,
            description="Newer",
            discovered_at=datetime(2025, 1, 2, 12, 0, 0),
            fetched_at=datetime(2025, 1, 2, 12, 0, 0),
        )

        database.save_source_snapshot(older)
        database.save_source_snapshot(newer)

        conn = database.get_connection()
        try:
            listing_row = conn.execute(
                "SELECT current_price, current_mileage, current_description, latest_source_snapshot_id FROM listings WHERE source_listing_id = ?",
                ("listing-2",),
            ).fetchone()
            self.assertEqual(listing_row[0], 43900)
            self.assertEqual(listing_row[1], 17850)
            self.assertEqual(listing_row[2], "Newer")
            self.assertIsNotNone(listing_row[3])
        finally:
            conn.close()

    def test_two_listings_same_vehicle_keep_independent_current_state(self):
        db_path = os.path.join(self.tempdir.name, "listing-two-per-vehicle.db")
        config.DATABASE = db_path
        database.get_connection().close()

        v1 = self._snapshot("autoscout24", "listing-a", price=44500, mileage=18400, vin="WAU123")
        v2 = self._snapshot("mobile_de", "listing-b", price=43950, mileage=18500, vin="WAU123")
        database.save_source_snapshot(v1)
        database.save_source_snapshot(v2)

        conn = database.get_connection()
        try:
            rows = conn.execute(
                "SELECT source_listing_id, current_price, current_mileage FROM listings ORDER BY source_listing_id"
            ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "listing-a")
            self.assertEqual(rows[0][1], 44500)
            self.assertEqual(rows[0][2], 18400)
            self.assertEqual(rows[1][0], "listing-b")
            self.assertEqual(rows[1][1], 43950)
            self.assertEqual(rows[1][2], 18500)
        finally:
            conn.close()

    def test_missing_fields_do_not_erase_previous_effective_values(self):
        db_path = os.path.join(self.tempdir.name, "listing-missing-field.db")
        config.DATABASE = db_path
        database.get_connection().close()

        first = self._snapshot("autoscout24", "listing-missing", price=40000, mileage=15000, description="Original", url="https://example.com/one")
        second = self._snapshot(
            "autoscout24",
            "listing-missing",
            price=39000,
            mileage=15000,
            description="Updated",
            url="https://example.com/two",
            discovered_at=datetime(2025, 2, 1, 12, 0, 0),
            fetched_at=datetime(2025, 2, 1, 12, 0, 0),
        )
        second.extracted_fields.pop("mileage")
        second.raw_summary_payload.pop("mileage", None)

        database.save_source_snapshot(first)
        database.save_source_snapshot(second)

        conn = database.get_connection()
        try:
            listing_row = conn.execute(
                "SELECT current_price, current_mileage, current_description, current_url FROM listings WHERE source_listing_id = ?",
                ("listing-missing",),
            ).fetchone()
            self.assertEqual(listing_row[0], 39000)
            self.assertEqual(listing_row[1], 15000)
            self.assertEqual(listing_row[2], "Updated")
            self.assertEqual(listing_row[3], "https://example.com/two")
        finally:
            conn.close()

    def test_dry_run_does_not_update_listing_current_state(self):
        db_path = os.path.join(self.tempdir.name, "listing-dry-run.db")
        config.DATABASE = db_path
        database.get_connection().close()

        snapshot = self._snapshot("autoscout24", "listing-dry", price=30000, mileage=20000)
        self.assertIsNone(database.save_source_snapshot(snapshot, dry_run=True))

        conn = database.get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            self.assertEqual(row, 0)
        finally:
            conn.close()


class TestMobileDeCredentials:
    """Test credential handling."""

    def test_credentials_from_environment(self, monkeypatch):
        """Test credentials loaded from environment variables."""
        import os
        from sources.mobile_de import MobileDeAPIClient

        monkeypatch.setenv("MOBILE_DE_API_USERNAME", "env_user")
        monkeypatch.setenv("MOBILE_DE_API_PASSWORD", "env_pass")

        client = MobileDeAPIClient()
        assert client.username == "env_user"
        assert client.password == "env_pass"
        assert client.credentials_available()

    def test_credentials_not_logged(self):
        """Test credentials are not accidentally logged."""
        from sources.mobile_de import MobileDeAPIClient

        client = MobileDeAPIClient(username="secret_user", password="secret_pass")
        # The repr/str should not contain credentials
        str_repr = str(client)
        assert "secret_user" not in str_repr
        assert "secret_pass" not in str_repr


class TestMobileDeErrorHandling:
    """Test error handling."""

    def test_missing_credentials_raises_error(self):
        """Test missing credentials raises proper error."""
        import os
        from sources.mobile_de import (
            MobileDeSourceAdapter,
            MobileDeAPIClient,
            SourceCredentialsError,
        )
        from sources.base import DiscoveryRequest, SourceContext

        # Ensure no credentials
        os.environ.pop("MOBILE_DE_API_USERNAME", None)
        os.environ.pop("MOBILE_DE_API_PASSWORD", None)

        adapter = MobileDeSourceAdapter()
        request = DiscoveryRequest()
        context = SourceContext(source_name="mobile_de")

        try:
            adapter.discover_listings(request, context)
            assert False, "Should have raised SourceCredentialsError"
        except SourceCredentialsError:
            pass  # Expected

    def test_malformed_listing_skipped(self):
        """Test malformed listing doesn't break discovery."""
        from sources.mobile_de import MobileDeSourceAdapter, MobileDeAPIClient
        from sources.base import DiscoveryRequest, SourceContext
        from unittest.mock import Mock, MagicMock
        from datetime import datetime

        # Create adapter with mocked API client
        mock_client = Mock(spec=MobileDeAPIClient)
        mock_client.credentials_available.return_value = True

        adapter = MobileDeSourceAdapter(api_client=mock_client)
        request = DiscoveryRequest()
        context = SourceContext(source_name="mobile_de")

        # Mock API response with one valid and one malformed ad
        mock_response = {
            "ads": [
                {
                    "mobileAdId": "valid1",
                    "detailPageUrl": "https://mobile.de/auto/valid1",
                    "make": "BMW",
                    "model": "3 Series",
                },
                {
                    # Malformed: missing mobileAdId
                    "detailPageUrl": "https://mobile.de/auto/invalid",
                    "make": "Audi",
                },
                {
                    "mobileAdId": "valid2",
                    "detailPageUrl": "https://mobile.de/auto/valid2",
                    "make": "Mercedes",
                    "model": "C-Class",
                },
            ],
            "currentPage": 1,
            "maxPages": 1,
        }

        mock_client.get_json.return_value = mock_response

        listings = adapter.discover_listings(request, context)

        # Should have 2 valid listings (malformed one skipped)
        assert len(listings) == 2
        assert listings[0].source_listing_id == "valid1"
        assert listings[1].source_listing_id == "valid2"



# ===========================================================================
# PKW.de Adapter Tests
# ===========================================================================

from datetime import datetime as _datetime


def _pkw_search_result(listing_id="681247396872418378", price_customer=38950):
    """Minimal realistic PKW.de search result (summary payload)."""
    return {
        "id": listing_id,
        "name": "Audi A5 Cabrio 40 2.0 TDI quattro S Line",
        "brand": {"id": 6, "name": "Audi"},
        "model": {"id": 992, "parent_id": 6, "name": "A5"},
        "bodytype": {"id": 2, "name": "Cabriolet"},
        "initial_registration": "2022-07-01",
        "mileage": 31142,
        "price": {
            "customer": price_customer,
            "price_type": None,
            "netto_price": 32731.0,
            "initial_price": 41000,
        },
        "fueltype": {"id": 2, "name": "Diesel"},
        "geartype": {"id": 2, "name": "Automatik"},
        "power": {"kw": 140, "hp": 190},
        "color": {
            "exterior": {"id": 1, "name": "Schwarz"},
            "interior": {"id": 4, "name": "Leder"},
        },
        "owner": {
            "id": "178360920259386597",
            "name": "Autohaus Muster GmbH",
            "type": "dealer",
            "phone": "0202-12345",
        },
        "location": {
            "country": "DE",
            "city": "Schwerte",
            "zip": "58239",
            "coordinates": {"lat": 51.4, "lon": 7.6},
        },
        "available_online": False,
        "deleted": False,
    }


def _pkw_detail_payload(listing_id="681247396872418378"):
    """Realistic PKW.de detail payload (superset of summary)."""
    base = _pkw_search_result(listing_id)
    base.update({
        "description": "<p></p><b>Ausstattung:</b> Navi, Kamera",
        "extras": [
            {"id": 0, "name": "ABS"},
            {"id": 3, "name": "Allradantrieb"},
            {"id": 4, "name": "Alufelgen"},
            {"id": 7, "name": "Bordcomputer"},
        ],
        "images": [
            {
                "thumb": "https://images.pkw.net/img-120x90.jpg",
                "full": "https://images.pkw.net/img-640x480.jpg",
                "original": "https://images.pkw.net/img-0x0.jpg",
            }
        ],
        "equipment_line": "S line",
    })
    return base


def _pkw_search_page(listing_ids, page=1, total_count=40, total_pages=2):
    return {
        "page": page,
        "total": {"count": total_count, "pages": total_pages},
        "links": [{"rel": "self", "href": f"https://www.pkw.de/api/v1/cars/search/basic?page={page}"}],
        "results": [_pkw_search_result(lid) for lid in listing_ids],
    }


class TestPkwDeAdapterRegistration:
    """1. Adapter is registered correctly."""

    def test_adapter_is_registered_in_default_registry(self):
        from sources import build_default_source_registry, PkwDeSourceAdapter
        registry = build_default_source_registry()
        adapter = registry.get("pkw_de")
        assert isinstance(adapter, PkwDeSourceAdapter)

    def test_adapter_source_name(self):
        from sources.pkw_de import PkwDeSourceAdapter
        adapter = PkwDeSourceAdapter(max_pages=1)
        assert adapter.descriptor().source_name == "pkw_de"

    def test_adapter_implements_source_adapter_protocol(self):
        from sources import PkwDeSourceAdapter, SourceAdapter
        adapter = PkwDeSourceAdapter(max_pages=1)
        assert isinstance(adapter, SourceAdapter)

    def test_source_name_in_snapshot_is_pkw_de(self):
        from sources.pkw_de import PkwDeSourceAdapter
        from sources.base import DiscoveredListing, SourceListingDetail
        adapter = PkwDeSourceAdapter(max_pages=1)
        listing = DiscoveredListing(
            source_name="pkw_de",
            source_listing_id="123",
            source_url="https://suche.pkw.de/fahrzeuge/details/123",
            discovered_at=_datetime.now(),
            raw_summary_payload=_pkw_search_result("123"),
        )
        snapshot = adapter.to_source_snapshot(listing, None)
        assert snapshot.source_name == "pkw_de"


class TestPkwDeDiscovery:
    """2–6. Search / discovery behaviour and pagination."""

    def _adapter_with_mock(self, pages_data):
        from sources.pkw_de import PkwDeSourceAdapter, PkwDeAPIClient
        from unittest.mock import Mock
        mock_client = Mock(spec=PkwDeAPIClient)
        mock_client.get_json.side_effect = pages_data
        return PkwDeSourceAdapter(max_pages=10, api_client=mock_client), mock_client

    def test_search_creates_discovered_listings(self):
        from sources.base import DiscoveryRequest, SourceContext
        page = _pkw_search_page(["681247396872418378", "727928327740362618"], page=1, total_count=2, total_pages=1)
        adapter, _ = self._adapter_with_mock([page])
        listings = adapter.discover_listings(DiscoveryRequest(), SourceContext(source_name="pkw_de"))
        assert len(listings) == 2

    def test_stable_listing_id_preserved(self):
        from sources.base import DiscoveryRequest, SourceContext
        page = _pkw_search_page(["681247396872418378"], page=1, total_count=1, total_pages=1)
        adapter, _ = self._adapter_with_mock([page])
        listings = adapter.discover_listings(DiscoveryRequest(), SourceContext(source_name="pkw_de"))
        assert listings[0].source_listing_id == "681247396872418378"

    def test_source_url_generated_correctly(self):
        from sources.base import DiscoveryRequest, SourceContext
        lid = "681247396872418378"
        page = _pkw_search_page([lid], page=1, total_count=1, total_pages=1)
        adapter, _ = self._adapter_with_mock([page])
        listings = adapter.discover_listings(DiscoveryRequest(), SourceContext(source_name="pkw_de"))
        assert listings[0].source_url == f"https://suche.pkw.de/fahrzeuge/details/{lid}"

    def test_pagination_across_multiple_pages(self):
        from sources.base import DiscoveryRequest, SourceContext
        p1 = _pkw_search_page(["a", "b"], page=1, total_count=4, total_pages=2)
        p2 = _pkw_search_page(["c", "d"], page=2, total_count=4, total_pages=2)
        adapter, mock_client = self._adapter_with_mock([p1, p2])
        listings = adapter.discover_listings(DiscoveryRequest(), SourceContext(source_name="pkw_de"))
        assert len(listings) == 4
        assert mock_client.get_json.call_count == 2

    def test_pagination_stops_at_total_pages(self):
        from sources.base import DiscoveryRequest, SourceContext
        p1 = _pkw_search_page(["a"], page=1, total_count=2, total_pages=2)
        p2 = _pkw_search_page(["b"], page=2, total_count=2, total_pages=2)
        adapter, mock_client = self._adapter_with_mock([p1, p2])
        adapter.max_pages = 100
        listings = adapter.discover_listings(DiscoveryRequest(), SourceContext(source_name="pkw_de"))
        assert len(listings) == 2
        assert mock_client.get_json.call_count == 2

    def test_empty_results_stops_pagination(self):
        from sources.base import DiscoveryRequest, SourceContext
        p1 = _pkw_search_page(["x"], page=1, total_count=1, total_pages=2)
        p_empty = {"page": 2, "total": {"count": 1, "pages": 2}, "results": []}
        adapter, mock_client = self._adapter_with_mock([p1, p_empty])
        listings = adapter.discover_listings(DiscoveryRequest(), SourceContext(source_name="pkw_de"))
        assert len(listings) == 1

    def test_duplicate_ids_across_pages_are_deduplicated(self):
        from sources.base import DiscoveryRequest, SourceContext
        p1 = _pkw_search_page(["dup-1", "dup-2"], page=1, total_count=2, total_pages=2)
        p2 = _pkw_search_page(["dup-1", "dup-2"], page=2, total_count=2, total_pages=2)
        adapter, _ = self._adapter_with_mock([p1, p2])
        listings = adapter.discover_listings(DiscoveryRequest(), SourceContext(source_name="pkw_de"))
        assert len(listings) == 2

    def test_missing_listing_id_is_skipped(self):
        from sources.base import DiscoveryRequest, SourceContext
        good = _pkw_search_result("good")
        no_id = dict(_pkw_search_result("x"))
        no_id.pop("id")
        page = {"page": 1, "total": {"count": 2, "pages": 1}, "results": [good, no_id]}
        adapter, _ = self._adapter_with_mock([page])
        listings = adapter.discover_listings(DiscoveryRequest(), SourceContext(source_name="pkw_de"))
        assert len(listings) == 1
        assert listings[0].source_listing_id == "good"


class TestPkwDeFieldNormalization:
    """7–16. Normalized field mapping."""

    def _snapshot(self, listing_id="681247396872418378"):
        from sources.pkw_de import PkwDeSourceAdapter
        from sources.base import DiscoveredListing, SourceListingDetail
        adapter = PkwDeSourceAdapter(max_pages=1)
        listing = DiscoveredListing(
            source_name="pkw_de",
            source_listing_id=listing_id,
            source_url=f"https://suche.pkw.de/fahrzeuge/details/{listing_id}",
            discovered_at=_datetime.now(),
            raw_summary_payload=_pkw_search_result(listing_id),
        )
        detail_obj = SourceListingDetail(
            source_name="pkw_de",
            source_listing_id=listing_id,
            fetched_at=_datetime.now(),
            raw_detail_payload=_pkw_detail_payload(listing_id),
        )
        return adapter.to_source_snapshot(listing, detail_obj)

    def test_price_customer_normalization(self):
        assert self._snapshot().extracted_fields["price"] == 38950

    def test_price_is_integer(self):
        assert isinstance(self._snapshot().extracted_fields["price"], int)

    def test_mileage_normalization(self):
        assert self._snapshot().extracted_fields["mileage"] == 31142

    def test_mileage_is_integer(self):
        assert isinstance(self._snapshot().extracted_fields["mileage"], int)

    def test_first_registration(self):
        assert self._snapshot().extracted_fields["first_registration"] == "2022-07-01"

    def test_year_from_registration(self):
        assert self._snapshot().extracted_fields["year"] == 2022

    def test_make(self):
        assert self._snapshot().extracted_fields["make"] == "Audi"

    def test_model(self):
        assert self._snapshot().extracted_fields["model"] == "A5"

    def test_title(self):
        assert "Audi A5" in self._snapshot().extracted_fields["title"]

    def test_fuel(self):
        assert self._snapshot().extracted_fields["fuel"] == "Diesel"

    def test_transmission(self):
        assert self._snapshot().extracted_fields["transmission"] == "Automatik"

    def test_power_kw(self):
        assert self._snapshot().extracted_fields["power_kw"] == 140

    def test_power_hp(self):
        assert self._snapshot().extracted_fields["power_hp"] == 190

    def test_dealer_name(self):
        assert self._snapshot().extracted_fields["seller_name"] == "Autohaus Muster GmbH"

    def test_location_city(self):
        assert self._snapshot().extracted_fields["location_city"] == "Schwerte"

    def test_description_html_stripped(self):
        desc = self._snapshot().extracted_fields.get("description", "")
        assert "<" not in desc
        assert "Ausstattung" in desc

    def test_options_mapped(self):
        opts = self._snapshot().extracted_fields.get("options", [])
        assert "ABS" in opts
        assert "Alufelgen" in opts

    def test_drivetrain_awd_from_extras(self):
        assert self._snapshot().extracted_fields.get("drivetrain") == "AWD"

    def test_drivetrain_absent_without_awd_extras(self):
        from sources.pkw_de import PkwDeSourceAdapter
        from sources.base import DiscoveredListing, SourceListingDetail
        adapter = PkwDeSourceAdapter(max_pages=1)
        detail = _pkw_detail_payload("no-awd")
        detail["extras"] = [{"id": 0, "name": "ABS"}, {"id": 4, "name": "Alufelgen"}]
        listing = DiscoveredListing(
            source_name="pkw_de", source_listing_id="no-awd",
            source_url="https://suche.pkw.de/fahrzeuge/details/no-awd",
            discovered_at=_datetime.now(),
            raw_summary_payload=_pkw_search_result("no-awd"),
        )
        det = SourceListingDetail(source_name="pkw_de", source_listing_id="no-awd",
                                   fetched_at=_datetime.now(), raw_detail_payload=detail)
        snap = adapter.to_source_snapshot(listing, det)
        assert snap.extracted_fields.get("drivetrain") is None

    def test_colour(self):
        assert self._snapshot().extracted_fields.get("colour") == "Schwarz"


class TestPkwDeAvailability:
    """Availability mapping."""

    def _snap(self, deleted=False):
        from sources.pkw_de import PkwDeSourceAdapter
        from sources.base import DiscoveredListing
        adapter = PkwDeSourceAdapter(max_pages=1)
        raw = _pkw_search_result("av-test")
        raw["deleted"] = deleted
        listing = DiscoveredListing(
            source_name="pkw_de", source_listing_id="av-test",
            source_url="https://suche.pkw.de/fahrzeuge/details/av-test",
            discovered_at=_datetime.now(), raw_summary_payload=raw,
        )
        return adapter.to_source_snapshot(listing, None)

    def test_normal_listing_is_active(self):
        assert self._snap(deleted=False).extracted_fields["availability"] == "ACTIVE"

    def test_deleted_listing_is_inactive(self):
        assert self._snap(deleted=True).extracted_fields["availability"] == "INACTIVE"

    def test_availability_is_canonical_value(self):
        assert self._snap().extracted_fields["availability"] in {"ACTIVE", "INACTIVE", "SOLD", "UNKNOWN"}


class TestPkwDeDetailFetch:
    """17–18. Detail fetch and failure isolation."""

    def test_detail_fetch_success(self):
        from sources.pkw_de import PkwDeSourceAdapter, PkwDeAPIClient
        from sources.base import DiscoveredListing, SourceContext
        from unittest.mock import Mock
        mock_client = Mock(spec=PkwDeAPIClient)
        mock_client.get_json.return_value = _pkw_detail_payload("681247396872418378")
        adapter = PkwDeSourceAdapter(max_pages=1, api_client=mock_client)
        listing = DiscoveredListing(
            source_name="pkw_de", source_listing_id="681247396872418378",
            source_url="https://suche.pkw.de/fahrzeuge/details/681247396872418378",
            discovered_at=_datetime.now(),
            raw_summary_payload=_pkw_search_result("681247396872418378"),
        )
        detail = adapter.fetch_listing_detail(listing, SourceContext(source_name="pkw_de"))
        assert detail is not None
        assert detail.source_listing_id == "681247396872418378"

    def test_detail_failure_returns_none_not_exception(self):
        from sources.pkw_de import PkwDeSourceAdapter, PkwDeAPIClient, PkwDeAPIError
        from sources.base import DiscoveredListing, SourceContext
        from unittest.mock import Mock
        mock_client = Mock(spec=PkwDeAPIClient)
        mock_client.get_json.side_effect = PkwDeAPIError("timeout")
        adapter = PkwDeSourceAdapter(max_pages=1, api_client=mock_client)
        listing = DiscoveredListing(
            source_name="pkw_de", source_listing_id="bad",
            source_url="https://suche.pkw.de/fahrzeuge/details/bad",
            discovered_at=_datetime.now(),
            raw_summary_payload=_pkw_search_result("bad"),
        )
        detail = adapter.fetch_listing_detail(listing, SourceContext(source_name="pkw_de"))
        assert detail is None

    def test_snapshot_produced_without_detail(self):
        from sources.pkw_de import PkwDeSourceAdapter
        from sources.base import DiscoveredListing
        adapter = PkwDeSourceAdapter(max_pages=1)
        listing = DiscoveredListing(
            source_name="pkw_de", source_listing_id="no-det",
            source_url="https://suche.pkw.de/fahrzeuge/details/no-det",
            discovered_at=_datetime.now(),
            raw_summary_payload=_pkw_search_result("no-det"),
        )
        snap = adapter.to_source_snapshot(listing, None)
        assert snap is not None
        assert snap.raw_detail_payload is None

    def test_malformed_search_response_raises_pkwde_error(self):
        from sources.pkw_de import PkwDeSourceAdapter, PkwDeAPIClient, PkwDeAPIError
        from sources.base import DiscoveryRequest, SourceContext
        from unittest.mock import Mock
        mock_client = Mock(spec=PkwDeAPIClient)
        mock_client.get_json.side_effect = PkwDeAPIError("invalid JSON")
        adapter = PkwDeSourceAdapter(max_pages=1, api_client=mock_client)
        try:
            adapter.discover_listings(DiscoveryRequest(), SourceContext(source_name="pkw_de"))
            assert False, "Expected PkwDeAPIError"
        except PkwDeAPIError:
            pass


class TestPkwDeProvenance:
    """19. Field provenance source_name = pkw_de."""

    def test_all_provenance_entries_have_pkw_de_source_name(self):
        from sources.pkw_de import PkwDeSourceAdapter
        from sources.base import DiscoveredListing, SourceListingDetail
        adapter = PkwDeSourceAdapter(max_pages=1)
        listing = DiscoveredListing(
            source_name="pkw_de", source_listing_id="prov-1",
            source_url="https://suche.pkw.de/fahrzeuge/details/prov-1",
            discovered_at=_datetime.now(),
            raw_summary_payload=_pkw_search_result("prov-1"),
        )
        det = SourceListingDetail(
            source_name="pkw_de", source_listing_id="prov-1",
            fetched_at=_datetime.now(),
            raw_detail_payload=_pkw_detail_payload("prov-1"),
        )
        snap = adapter.to_source_snapshot(listing, det)
        for fname, prov in snap.field_provenance.items():
            assert prov["source_name"] == "pkw_de", f"Field {fname!r} has wrong source_name"
            assert prov["source_listing_id"] == "prov-1"


class TestPkwDeCanonicalPersistence:
    """20–21. Canonical persistence and coexistence with AutoScout24."""

    def test_canonical_persistence_accepts_pkw_snapshot(self):
        import os
        import tempfile as _tempfile
        db_path = os.path.join(_tempfile.mkdtemp(), "pkw-canon.db")
        orig = config.DATABASE
        config.DATABASE = db_path
        database.get_connection().close()
        try:
            snap = SourceSnapshot(
                source_name="pkw_de",
                source_listing_id="681247396872418378",
                source_url="https://suche.pkw.de/fahrzeuge/details/681247396872418378",
                discovered_at=_datetime.now(),
                fetched_at=_datetime.now(),
                raw_summary_payload=_pkw_search_result("681247396872418378"),
                raw_detail_payload=_pkw_detail_payload("681247396872418378"),
                extracted_fields={"make": "Audi", "price": 38950},
                field_provenance={"price": {"source_name": "pkw_de", "source_listing_id": "681247396872418378", "stage": "summary"}},
            )
            row_id = database.save_source_snapshot(snap)
            assert row_id is not None
            conn = database.get_connection()
            try:
                row = conn.execute("SELECT source_name FROM sources WHERE source_name = ?", ("pkw_de",)).fetchone()
                assert row is not None
            finally:
                conn.close()
        finally:
            config.DATABASE = orig

    def test_pkw_and_autoscout24_coexist(self):
        import os
        import tempfile as _tempfile
        db_path = os.path.join(_tempfile.mkdtemp(), "pkw-dual.db")
        orig = config.DATABASE
        config.DATABASE = db_path
        database.get_connection().close()
        try:
            pkw_snap = SourceSnapshot(
                source_name="pkw_de",
                source_listing_id="pkw-co-1",
                source_url="https://suche.pkw.de/fahrzeuge/details/pkw-co-1",
                discovered_at=_datetime.now(), fetched_at=_datetime.now(),
                raw_summary_payload={"id": "pkw-co-1"},
                raw_detail_payload=None,
                extracted_fields={"price": 30000},
                field_provenance={"price": {"source_name": "pkw_de", "source_listing_id": "pkw-co-1", "stage": "summary"}},
            )
            as24_snap = SourceSnapshot(
                source_name="autoscout24",
                source_listing_id="as24-co-1",
                source_url="https://www.autoscout24.de/angebote/as24-co-1",
                discovered_at=_datetime.now(), fetched_at=_datetime.now(),
                raw_summary_payload={"id": "as24-co-1"},
                raw_detail_payload=None,
                extracted_fields={"price": 25000},
                field_provenance={"price": {"source_name": "autoscout24", "source_listing_id": "as24-co-1", "stage": "summary"}},
            )
            database.save_source_snapshot(pkw_snap)
            database.save_source_snapshot(as24_snap)
            conn = database.get_connection()
            try:
                sources = {r[0] for r in conn.execute("SELECT source_name FROM sources").fetchall()}
                assert "pkw_de" in sources
                assert "autoscout24" in sources
                count = conn.execute("SELECT COUNT(*) FROM source_listings").fetchone()[0]
                assert count == 2
            finally:
                conn.close()
        finally:
            config.DATABASE = orig


# ---------------------------------------------------------------------------
# Portal source-identity tests
# ---------------------------------------------------------------------------

class TestPortalSourceIdentity(unittest.TestCase):
    """Tests for source_name / source_label enrichment in portal Car objects."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.orig_db = config.DATABASE
        config.DATABASE = os.path.join(self.tempdir.name, "portal_test.db")
        conn = database.get_connection()
        conn.close()
        # Insert two sources
        conn = database.get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO sources (source_name, display_name) VALUES (?, ?)",
            ("autoscout24", "AutoScout24"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO sources (source_name, display_name) VALUES (?, ?)",
            ("pkw_de", "PKW.de"),
        )
        conn.commit()
        # Get source ids
        as24_id = conn.execute("SELECT id FROM sources WHERE source_name='autoscout24'").fetchone()[0]
        pkw_id = conn.execute("SELECT id FROM sources WHERE source_name='pkw_de'").fetchone()[0]
        # Insert source_listings
        conn.execute(
            "INSERT INTO source_listings (source_id, source_listing_id, source_url) VALUES (?, ?, ?)",
            (as24_id, "as24-1", "https://www.autoscout24.de/angebote/as24-1"),
        )
        conn.execute(
            "INSERT INTO source_listings (source_id, source_listing_id, source_url) VALUES (?, ?, ?)",
            (pkw_id, "pkw-1", "https://suche.pkw.de/fahrzeuge/details/pkw-1"),
        )
        conn.commit()
        now = _datetime.now().isoformat()
        # Insert cars referencing those URLs
        conn.execute(
            "INSERT INTO cars (title, price, km, url, first_seen, last_seen, final_score, personal_score, sold) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Audi A5 AutoScout24", 30000, 50000, "https://www.autoscout24.de/angebote/as24-1", now, now, 70, 0, 0),
        )
        conn.execute(
            "INSERT INTO cars (title, price, km, url, first_seen, last_seen, final_score, personal_score, sold) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Audi A5 PKW.de", 28000, 35000, "https://suche.pkw.de/fahrzeuge/details/pkw-1", now, now, 65, 0, 0),
        )
        # A car with no resolvable source (legacy / pre-fix row with no url)
        conn.execute(
            "INSERT INTO cars (title, price, km, url, first_seen, last_seen, final_score, personal_score, sold) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Audi A5 Unknown", 20000, None, None, now, now, 40, 0, 0),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        config.DATABASE = self.orig_db
        self.tempdir.cleanup()

    def test_autoscout24_car_source_label(self):
        cars = database.get_ranking(limit=10)
        as24 = next((c for c in cars if "AutoScout24" in c.title), None)
        self.assertIsNotNone(as24)
        self.assertEqual(as24.source_name, "autoscout24")
        self.assertEqual(as24.source_label, "AutoScout24")

    def test_pkw_de_car_source_label(self):
        cars = database.get_ranking(limit=10)
        pkw = next((c for c in cars if "PKW.de" in c.title), None)
        self.assertIsNotNone(pkw)
        self.assertEqual(pkw.source_name, "pkw_de")
        self.assertEqual(pkw.source_label, "PKW.de")

    def test_unknown_source_fallback(self):
        cars = database.get_ranking(limit=10)
        unknown = next((c for c in cars if "Unknown" in c.title), None)
        self.assertIsNotNone(unknown)
        self.assertIsNone(unknown.source_name)
        self.assertEqual(unknown.source_label, "Listing")

    def test_no_duplicate_rows_from_enrichment(self):
        """Enrichment must not multiply Car rows."""
        cars = database.get_ranking(limit=10)
        self.assertEqual(len(cars), 3)

    def test_ranking_contains_both_sources(self):
        cars = database.get_ranking(limit=10)
        source_labels = {c.source_label for c in cars}
        self.assertIn("AutoScout24", source_labels)
        self.assertIn("PKW.de", source_labels)

    def test_get_car_enriched(self):
        """get_car() must enrich the single result with source identity."""
        conn = database.get_connection()
        row = conn.execute("SELECT id FROM cars WHERE title='Audi A5 AutoScout24'").fetchone()
        conn.close()
        car = database.get_car(row[0])
        self.assertEqual(car.source_name, "autoscout24")
        self.assertEqual(car.source_label, "AutoScout24")

    def test_search_cars_enriched(self):
        cars = database.search_cars()
        as24 = next((c for c in cars if "AutoScout24" in c.title), None)
        self.assertIsNotNone(as24)
        self.assertEqual(as24.source_label, "AutoScout24")

    def test_source_counts_both_sources(self):
        counts = database.get_source_counts()
        self.assertIn("AutoScout24", counts)
        self.assertIn("PKW.de", counts)
        self.assertEqual(counts["AutoScout24"], 1)
        self.assertEqual(counts["PKW.de"], 1)

    def test_source_counts_excludes_sold(self):
        """Sold cars must not appear in source_counts."""
        conn = database.get_connection()
        conn.execute("UPDATE cars SET sold=1 WHERE title='Audi A5 AutoScout24'")
        conn.commit()
        conn.close()
        counts = database.get_source_counts()
        self.assertEqual(counts.get("AutoScout24", 0), 0)
        self.assertEqual(counts.get("PKW.de", 1), 1)

    def test_source_counts_does_not_hardcode_source_names(self):
        """Source counts must be driven by DB metadata, not hard-coded keys."""
        # Add a third fictional source and verify it appears automatically
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO sources (source_name, display_name) VALUES (?, ?)",
            ("future_source", "FutureAuto"),
        )
        future_id = conn.execute("SELECT id FROM sources WHERE source_name='future_source'").fetchone()[0]
        conn.execute(
            "INSERT INTO source_listings (source_id, source_listing_id, source_url) VALUES (?, ?, ?)",
            (future_id, "fa-1", "https://futureauto.example.com/listing/1"),
        )
        now = _datetime.now().isoformat()
        conn.execute(
            "INSERT INTO cars (title, url, first_seen, last_seen, sold, final_score, personal_score) VALUES (?,?,?,?,?,?,?)",
            ("Future Car", "https://futureauto.example.com/listing/1", now, now, 0, 50, 0),
        )
        conn.commit()
        conn.close()
        counts = database.get_source_counts()
        self.assertIn("FutureAuto", counts)

    def test_car_model_source_defaults(self):
        """A freshly constructed Car from a bare row must have safe source defaults."""
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(config.DATABASE)
        row = conn.execute("SELECT * FROM cars WHERE title='Audi A5 Unknown'").fetchone()
        conn.close()
        from models import Car
        car = Car(row)
        # Before enrichment: defaults
        self.assertIsNone(car.source_name)
        self.assertEqual(car.source_label, "Listing")


class TestSaveCarUrlIdempotency(unittest.TestCase):
    """Regression tests for url-based deduplication in save_car().

    PKW.de rows have no fingerprint and no autoscout_id.  Without the url
    fallback, save_car would INSERT a new row on every pipeline run.

    Uses an isolated temporary database so results are deterministic and
    independent of live inventory.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.orig_db = config.DATABASE
        config.DATABASE = os.path.join(self.tempdir.name, "idem_test.db")
        database.get_connection().close()

    def tearDown(self):
        config.DATABASE = self.orig_db
        self.tempdir.cleanup()

    def test_save_car_deduplicates_on_url_when_no_fingerprint(self):
        """Second save_car call with same url must update, not insert."""
        car = {
            "title": "Audi A5 PKWde idem",
            "price": 29900,
            "km": 50000,
            "year": "2022",
            "url": "https://suche.pkw.de/fahrzeuge/details/idem_test_1",
        }
        is_new_first = database.save_car(car)
        is_new_second = database.save_car({**car, "price": 28000})

        self.assertTrue(is_new_first, "First insert must be new")
        self.assertFalse(is_new_second, "Second call with same url must not be new")

        conn = database.get_connection()
        rows = conn.execute(
            "SELECT COUNT(*), price FROM cars WHERE url=?",
            ("https://suche.pkw.de/fahrzeuge/details/idem_test_1",)
        ).fetchone()
        conn.close()
        self.assertEqual(rows[0], 1, "Must not create duplicate rows")
        self.assertEqual(rows[1], 28000, "Price must be updated in-place")

    def test_save_car_url_fallback_does_not_affect_fingerprint_rows(self):
        """Fingerprint-keyed rows must still deduplicate on fingerprint, not url."""
        car = {
            "title": "Audi A5 fp idem",
            "price": 35000,
            "fingerprint": "fp-idem-b",
            "url": "https://www.autoscout24.de/angebote/idem_b",
        }
        is_new_first = database.save_car(car)
        is_new_second = database.save_car({**car, "url": "https://changed.url/b"})
        self.assertTrue(is_new_first)
        self.assertFalse(is_new_second, "Fingerprint match must still prevent duplicate")

        conn = database.get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM cars WHERE fingerprint='fp-idem-b'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_save_car_url_fallback_is_no_op_without_url(self):
        """A row with no fingerprint, no autoscout_id and no url inserts each time."""
        car = {"title": "Audi A5 keyless", "price": 9999}
        r1 = database.save_car(car)
        # A second keyless insert creates a second row — acknowledged limitation.
        self.assertTrue(r1)
        conn = database.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM cars WHERE title='Audi A5 keyless'").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 1)

    def test_dry_run_compatibility_detects_existing_url_row(self):
        """Dry-run new_cars count must be 0 when a matching url row already exists."""
        from source_compatibility import apply_compatibility_inventory_updates
        url = "https://suche.pkw.de/fahrzeuge/details/idem_dryrun_1"
        database.save_car({"title": "Audi A5 dryrun", "price": 30000, "url": url})

        snapshot = mock.Mock()
        snapshot.extracted_fields = {"title": "Audi A5 dryrun", "price": 30000}
        snapshot.source_url = url

        result = apply_compatibility_inventory_updates([snapshot], [], dry_run=True)
        self.assertEqual(result.new_cars, 0, "Existing url row must be detected in dry-run")


class TestPkwDeLegacyDuplicateRepair(unittest.TestCase):
    """Regression tests for the PKW.de legacy duplicate repair logic.

    All tests use an isolated temporary database populated with controlled
    fixtures.  No assertions on live inventory IDs or counts.
    """

    # PKW.de source_id used throughout fixtures
    _PKWDE_SOURCE_ID = 2

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.orig_db = config.DATABASE
        config.DATABASE = os.path.join(self.tempdir.name, "repair_test.db")
        database.get_connection().close()
        self._populate_fixtures()

    def tearDown(self):
        config.DATABASE = self.orig_db
        self.tempdir.cleanup()

    def _populate_fixtures(self):
        """
        Build a minimal database that mirrors the real pre/post-fix situation:

        Rows inserted:
          sources:           autoscout24, pkw_de
          source_listings:   sl_pkw (PKW.de), sl_as24 (AutoScout24), sl_pkw2 (ambiguous pair)
          source_snapshots:  one per source_listing
          cars:
            broken_id   — pre-fix row (url=NULL, km=NULL, first_seen in pre-fix batch)
            correct_id  — post-fix row (url=sl_pkw.source_url, km=19500)
            as24_id     — unrelated AutoScout24 row (must not be touched)
            broken2_id  — a second pre-fix row (for ambiguity test below)
            correct2_id — a second post-fix row that would pair with broken2
            broken3_id  — a pre-fix row with same price/title as broken2 (ambiguous)
        """
        conn = database.get_connection()

        # Sources
        conn.execute("INSERT INTO sources (source_name, display_name) VALUES ('autoscout24','AutoScout24')")
        conn.execute("INSERT INTO sources (source_name, display_name) VALUES ('pkw_de','PKW.de')")
        as24_sid = conn.execute("SELECT id FROM sources WHERE source_name='autoscout24'").fetchone()[0]
        pkw_sid  = conn.execute("SELECT id FROM sources WHERE source_name='pkw_de'").fetchone()[0]

        # Source listings
        conn.execute(
            "INSERT INTO source_listings (source_id, source_listing_id, source_url) VALUES (?,?,?)",
            (pkw_sid, "listing-pkw-1", "https://suche.pkw.de/fahrzeuge/details/listing-pkw-1"),
        )
        conn.execute(
            "INSERT INTO source_listings (source_id, source_listing_id, source_url) VALUES (?,?,?)",
            (as24_sid, "listing-as24-1", "https://www.autoscout24.de/angebote/listing-as24-1"),
        )
        # For ambiguity test: two PKW.de listings with the same title+price
        conn.execute(
            "INSERT INTO source_listings (source_id, source_listing_id, source_url) VALUES (?,?,?)",
            (pkw_sid, "listing-pkw-2a", "https://suche.pkw.de/fahrzeuge/details/listing-pkw-2a"),
        )
        conn.execute(
            "INSERT INTO source_listings (source_id, source_listing_id, source_url) VALUES (?,?,?)",
            (pkw_sid, "listing-pkw-2b", "https://suche.pkw.de/fahrzeuge/details/listing-pkw-2b"),
        )

        # Source snapshots (price+title used by repair query)
        conn.execute(
            """INSERT INTO source_snapshots
               (source_id, source_listing_id, snapshot_hash, extracted_fields, discovered_at, fetched_at)
               VALUES (?,?,?,?,datetime('now'),datetime('now'))""",
            (pkw_sid, "listing-pkw-1", "hash-pkw-1",
             '{"price": 47650, "title": "Audi A5 Test Cabrio", "mileage": 19500}'),
        )
        conn.execute(
            """INSERT INTO source_snapshots
               (source_id, source_listing_id, snapshot_hash, extracted_fields, discovered_at, fetched_at)
               VALUES (?,?,?,?,datetime('now'),datetime('now'))""",
            (as24_sid, "listing-as24-1", "hash-as24-1",
             '{"price": 35000, "title": "Audi A5 AS24 Car", "km": 80000, "fingerprint": "fp-as24-1"}'),
        )
        # Ambiguous: two PKW.de listings with identical title+price
        for lid in ("listing-pkw-2a", "listing-pkw-2b"):
            conn.execute(
                """INSERT INTO source_snapshots
                   (source_id, source_listing_id, snapshot_hash, extracted_fields, discovered_at, fetched_at)
                   VALUES (?,?,?,?,datetime('now'),datetime('now'))""",
                (pkw_sid, lid, f"hash-{lid}",
                 '{"price": 22000, "title": "Audi A5 Ambiguous"}'),
            )

        # Cars
        pre_fix_ts = "2026-08-14T17:55:00.000000"
        post_fix_ts = "2026-08-14T19:06:00.000000"

        # broken row (pre-fix PKW.de — url=NULL, km=NULL)
        conn.execute(
            "INSERT INTO cars (title, price, url, km, first_seen, last_seen, sold) VALUES (?,?,NULL,NULL,?,?,0)",
            ("Audi A5 Test Cabrio", 47650, pre_fix_ts, pre_fix_ts),
        )
        self.broken_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # correct replacement (post-fix PKW.de — url and km set)
        conn.execute(
            "INSERT INTO cars (title, price, url, km, first_seen, last_seen, sold) VALUES (?,?,?,?,?,?,0)",
            ("Audi A5 Test Cabrio", 47650,
             "https://suche.pkw.de/fahrzeuge/details/listing-pkw-1",
             19500, post_fix_ts, post_fix_ts),
        )
        self.correct_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # unrelated AutoScout24 row
        conn.execute(
            "INSERT INTO cars (title, price, url, km, fingerprint, first_seen, last_seen, sold) VALUES (?,?,?,?,?,?,?,0)",
            ("Audi A5 AS24 Car", 35000,
             "https://www.autoscout24.de/angebote/listing-as24-1",
             80000, "fp-as24-1", post_fix_ts, post_fix_ts),
        )
        self.as24_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # ambiguous pre-fix pair (same title+price, two different PKW.de listings)
        conn.execute(
            "INSERT INTO cars (title, price, url, km, first_seen, last_seen, sold) VALUES (?,?,NULL,NULL,?,?,0)",
            ("Audi A5 Ambiguous", 22000, pre_fix_ts, pre_fix_ts),
        )
        self.broken_ambig_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # post-fix rows for each ambiguous listing
        conn.execute(
            "INSERT INTO cars (title, price, url, km, first_seen, last_seen, sold) VALUES (?,?,?,?,?,?,0)",
            ("Audi A5 Ambiguous", 22000,
             "https://suche.pkw.de/fahrzeuge/details/listing-pkw-2a",
             50000, post_fix_ts, post_fix_ts),
        )
        self.correct_ambig_a = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO cars (title, price, url, km, first_seen, last_seen, sold) VALUES (?,?,?,?,?,?,0)",
            ("Audi A5 Ambiguous", 22000,
             "https://suche.pkw.de/fahrzeuge/details/listing-pkw-2b",
             50000, post_fix_ts, post_fix_ts),
        )
        self.correct_ambig_b = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.commit()
        conn.close()

    def _run_repair(self, execute=False):
        """Run the repair logic directly against the test DB."""
        import repair_pkwde_legacy_duplicates as repair
        # Temporarily override the timestamp prefix and source_id used by the repair
        orig_prefix = repair._PREFIX_RUN_TIMESTAMP_PREFIX
        orig_source_id = repair._PKWDE_SOURCE_ID
        repair._PREFIX_RUN_TIMESTAMP_PREFIX = "2026-08-14T17:55"
        repair._PKWDE_SOURCE_ID = self._PKWDE_SOURCE_ID
        try:
            return repair.run(execute=execute)
        finally:
            repair._PREFIX_RUN_TIMESTAMP_PREFIX = orig_prefix
            repair._PKWDE_SOURCE_ID = orig_source_id

    def test_provable_duplicate_is_soft_deleted(self):
        """Category A pre-fix row must become sold=1 after execute."""
        self._run_repair(execute=True)
        conn = database.get_connection()
        row = conn.execute("SELECT sold, recommendation FROM cars WHERE id=?", (self.broken_id,)).fetchone()
        conn.close()
        self.assertEqual(row[0], 1, "broken pre-fix row must be soft-deleted")
        self.assertEqual(row[1], "superseded_by_prefix_fix")

    def test_replacement_remains_active(self):
        """The correct post-fix row must remain sold=0 after repair."""
        self._run_repair(execute=True)
        conn = database.get_connection()
        row = conn.execute("SELECT sold, url, km FROM cars WHERE id=?", (self.correct_id,)).fetchone()
        conn.close()
        self.assertEqual(row[0], 0, "post-fix replacement must stay active")
        self.assertIn("listing-pkw-1", row[1])
        self.assertEqual(row[2], 19500)

    def test_ambiguous_candidate_is_not_touched(self):
        """When two post-fix rows match the same title+price the pre-fix row must be skipped."""
        self._run_repair(execute=True)
        conn = database.get_connection()
        row = conn.execute("SELECT sold FROM cars WHERE id=?", (self.broken_ambig_id,)).fetchone()
        conn.close()
        self.assertEqual(row[0], 0, "ambiguous pre-fix row must NOT be soft-deleted")

    def test_autoscout24_row_unaffected(self):
        """AutoScout24 cars must not be touched."""
        self._run_repair(execute=True)
        conn = database.get_connection()
        row = conn.execute("SELECT sold FROM cars WHERE id=?", (self.as24_id,)).fetchone()
        conn.close()
        self.assertEqual(row[0], 0, "AS24 car must remain active")

    def test_source_listings_unchanged(self):
        """Repair must not modify source_listings."""
        conn = database.get_connection()
        before = conn.execute("SELECT COUNT(*) FROM source_listings").fetchone()[0]
        conn.close()
        self._run_repair(execute=True)
        conn = database.get_connection()
        after = conn.execute("SELECT COUNT(*) FROM source_listings").fetchone()[0]
        conn.close()
        self.assertEqual(before, after)

    def test_source_snapshots_unchanged(self):
        """Repair must not modify source_snapshots."""
        conn = database.get_connection()
        before = conn.execute("SELECT COUNT(*) FROM source_snapshots").fetchone()[0]
        conn.close()
        self._run_repair(execute=True)
        conn = database.get_connection()
        after = conn.execute("SELECT COUNT(*) FROM source_snapshots").fetchone()[0]
        conn.close()
        self.assertEqual(before, after)

    def test_dry_run_makes_no_changes(self):
        """Dry-run must not modify any row."""
        self._run_repair(execute=False)
        conn = database.get_connection()
        sold_count = conn.execute(
            "SELECT COUNT(*) FROM cars WHERE COALESCE(sold,0)=1"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(sold_count, 0, "dry-run must change nothing")

    def test_second_execution_is_idempotent(self):
        """Running repair twice must change zero rows on the second pass."""
        self._run_repair(execute=True)
        # Run again; check the log to confirm 0 changes
        conn_before = database.get_connection()
        run_count_before = conn_before.execute("SELECT COUNT(*) FROM repair_runs").fetchone()[0]
        conn_before.close()

        self._run_repair(execute=True)

        conn_after = database.get_connection()
        run_count_after = conn_after.execute("SELECT COUNT(*) FROM repair_runs").fetchone()[0]
        last_report = conn_after.execute(
            "SELECT report FROM repair_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        conn_after.close()

        import json as _json
        report = _json.loads(last_report)
        self.assertEqual(run_count_after, run_count_before + 1, "second run must still log")
        self.assertEqual(report["rows_changed"], 0, "second run must change zero rows")


# ---------------------------------------------------------------------------
# Cross-source duplicate detection tests
# ---------------------------------------------------------------------------

class TestDuplicateDetection(unittest.TestCase):
    """
    Regression tests for duplicate_detection.py.

    All tests use isolated temporary databases populated with controlled
    fixtures — no dependency on live inventory IDs or counts.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.orig_db = config.DATABASE
        config.DATABASE = os.path.join(self.tempdir.name, "dup_test.db")
        database.get_connection().close()
        import duplicate_detection as _dd
        self._dd = _dd
        self._conn = database.get_connection()
        _dd.ensure_schema(self._conn)
        self._conn.commit()
        self._populate_fixtures()

    def tearDown(self):
        self._conn.close()
        config.DATABASE = self.orig_db
        self.tempdir.cleanup()

    # ── fixture helpers ────────────────────────────────────────────────────

    def _add_source(self, name, display_name=None):
        self._conn.execute(
            "INSERT OR IGNORE INTO sources (source_name, display_name) VALUES (?,?)",
            (name, display_name or name),
        )
        return self._conn.execute("SELECT id FROM sources WHERE source_name=?", (name,)).fetchone()[0]

    def _add_source_listing(self, source_id, listing_id, url):
        self._conn.execute(
            "INSERT INTO source_listings (source_id, source_listing_id, source_url) VALUES (?,?,?)",
            (source_id, listing_id, url),
        )
        return self._conn.execute(
            "SELECT id FROM source_listings WHERE source_id=? AND source_listing_id=?",
            (source_id, listing_id),
        ).fetchone()[0]

    def _add_snapshot(self, source_id, listing_id, fields: dict):
        import json as _json
        sl_row = self._conn.execute(
            "SELECT id FROM source_listings WHERE source_id=? AND source_listing_id=?",
            (source_id, listing_id),
        ).fetchone()
        sl_id = sl_row[0]
        snap_hash = f"hash-{listing_id}-{source_id}"
        self._conn.execute(
            """INSERT OR IGNORE INTO source_snapshots
               (source_id, source_listing_id, snapshot_hash, extracted_fields, discovered_at, fetched_at)
               VALUES (?,?,?,?,datetime('now'),datetime('now'))""",
            (source_id, listing_id, snap_hash, _json.dumps(fields)),
        )
        return self._conn.execute(
            "SELECT id FROM source_snapshots WHERE source_id=? AND source_listing_id=?",
            (source_id, listing_id),
        ).fetchone()[0]

    def _add_listing(self, source_id, source_listing_id, sl_row_id, snap_id,
                     price, mileage, seller, description=None, options=None):
        self._conn.execute(
            """INSERT INTO listings
               (source_id, source_listing_id, source_listing_row_id,
                current_price, current_mileage, current_seller,
                current_description, current_options,
                latest_source_snapshot_id, availability)
               VALUES (?,?,?,?,?,?,?,?,?,'ACTIVE')""",
            (source_id, source_listing_id, sl_row_id,
             price, mileage, seller, description, options, snap_id),
        )
        return self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _populate_fixtures(self):
        """Build a minimal cross-source fixture set."""
        sid_as24 = self._add_source("autoscout24", "AutoScout24")
        sid_pkw  = self._add_source("pkw_de", "PKW.de")
        self.sid_as24 = sid_as24
        self.sid_pkw  = sid_pkw

        # ── Pair A: exact duplicate (same vehicle on two sources) ───────────
        sl_a1 = self._add_source_listing(sid_as24, "as24-dup-1",
                                         "https://www.autoscout24.de/angebote/as24-dup-1")
        snap_a1 = self._add_snapshot(sid_as24, "as24-dup-1", {
            "title": "Audi A5 45 TFSI",
            "price": 47650, "km": 19500, "year": 2024,
            "hp": 265, "drive": "Allrad", "gearbox": "Automatik",
            "color": "grau",
        })
        self.lid_a1 = self._add_listing(
            sid_as24, "as24-dup-1", sl_a1, snap_a1,
            47650, 19500,
            "Autocenter Neuss GmbH & Co. KG",
        )

        sl_p1 = self._add_source_listing(sid_pkw, "pkw-dup-1",
                                         "https://suche.pkw.de/fahrzeuge/details/pkw-dup-1")
        snap_p1 = self._add_snapshot(sid_pkw, "pkw-dup-1", {
            "title": "Audi A5 Cabriolet 45 TFSI quattro S line ACC+RFK+NAVI",
            "price": 47650, "mileage": 19500, "year": 2024,
            "first_registration": "2024-08-01",
            "power_hp": 265, "drivetrain": "AWD", "transmission": "Automatik",
            "colour": "grau", "seller_name": "AUTOCENTER NEUSS GmbH & Co. KG",
        })
        self.lid_p1 = self._add_listing(
            sid_pkw, "pkw-dup-1", sl_p1, snap_p1,
            47650, 19500,
            "AUTOCENTER NEUSS GmbH & Co. KG",
            description="Long description with equipment list ACC NAVI Matrix LED Sportsitze",
        )

        # ── Pair B: same model/year but clearly different (mileage/price diff) ──
        sl_a2 = self._add_source_listing(sid_as24, "as24-diff-2",
                                         "https://www.autoscout24.de/angebote/as24-diff-2")
        snap_a2 = self._add_snapshot(sid_as24, "as24-diff-2", {
            "title": "Audi A5 45 TFSI", "price": 47650, "km": 75000,
            "year": 2024, "hp": 265, "drive": "Allrad", "gearbox": "Automatik",
        })
        self.lid_a2 = self._add_listing(
            sid_as24, "as24-diff-2", sl_a2, snap_a2,
            47650, 75000, "Another Dealer AG",
        )

        sl_p2 = self._add_source_listing(sid_pkw, "pkw-diff-2",
                                         "https://suche.pkw.de/fahrzeuge/details/pkw-diff-2")
        snap_p2 = self._add_snapshot(sid_pkw, "pkw-diff-2", {
            "title": "Audi A5 Cabriolet 45 TFSI S line", "price": 47650,
            "mileage": 19500, "year": 2024, "power_hp": 265,
            "seller_name": "Autohaus Schmidt",
        })
        self.lid_p2 = self._add_listing(
            sid_pkw, "pkw-diff-2", sl_p2, snap_p2,
            47650, 19500, "Autohaus Schmidt",
        )

        # ── Pair C: conflicting VIN ─────────────────────────────────────────
        sl_a3 = self._add_source_listing(sid_as24, "as24-vin-3",
                                         "https://www.autoscout24.de/angebote/as24-vin-3")
        snap_a3 = self._add_snapshot(sid_as24, "as24-vin-3", {
            "title": "Audi A5 40 TFSI", "price": 35000, "km": 50000,
            "year": 2022, "vin": "WAUZZZ8T0PA000001",
        })
        self.lid_a3 = self._add_listing(
            sid_as24, "as24-vin-3", sl_a3, snap_a3,
            35000, 50000, "Dealer One",
        )

        sl_p3 = self._add_source_listing(sid_pkw, "pkw-vin-3",
                                         "https://suche.pkw.de/fahrzeuge/details/pkw-vin-3")
        snap_p3 = self._add_snapshot(sid_pkw, "pkw-vin-3", {
            "title": "Audi A5 40 TFSI", "price": 35000, "mileage": 50000,
            "year": 2022, "vin": "WAUZZZ8T0PA999999",
        })
        self.lid_p3 = self._add_listing(
            sid_pkw, "pkw-vin-3", sl_p3, snap_p3,
            35000, 50000, "Dealer One",
        )

        # ── Pair D: same source (must be ignored) ──────────────────────────
        sl_a4 = self._add_source_listing(sid_as24, "as24-same-4",
                                         "https://www.autoscout24.de/angebote/as24-same-4")
        snap_a4 = self._add_snapshot(sid_as24, "as24-same-4", {
            "title": "Audi A5 45 TFSI", "price": 47650, "km": 19500, "year": 2024,
        })
        self.lid_a4 = self._add_listing(
            sid_as24, "as24-same-4", sl_a4, snap_a4,
            47650, 19500, "Autocenter Neuss GmbH",
        )

        # ── Pair E: same title but different seller ─────────────────────────
        sl_a5 = self._add_source_listing(sid_as24, "as24-sell-5",
                                         "https://www.autoscout24.de/angebote/as24-sell-5")
        snap_a5 = self._add_snapshot(sid_as24, "as24-sell-5", {
            "title": "Audi A5 Cabriolet 40 TFSI", "price": 32000,
            "km": 45000, "year": 2021, "hp": 204,
        })
        self.lid_a5 = self._add_listing(
            sid_as24, "as24-sell-5", sl_a5, snap_a5,
            32000, 45000, "Autohaus Müller GmbH",
        )

        sl_p5 = self._add_source_listing(sid_pkw, "pkw-sell-5",
                                         "https://suche.pkw.de/fahrzeuge/details/pkw-sell-5")
        snap_p5 = self._add_snapshot(sid_pkw, "pkw-sell-5", {
            "title": "Audi A5 Cabriolet 40 TFSI S line", "price": 32000,
            "mileage": 45000, "year": 2021, "power_hp": 204,
            "seller_name": "Fahrzeugcenter Berlin",
        })
        self.lid_p5 = self._add_listing(
            sid_pkw, "pkw-sell-5", sl_p5, snap_p5,
            32000, 45000, "Fahrzeugcenter Berlin",
        )

        self._conn.commit()

    # ── Tests ──────────────────────────────────────────────────────────────

    def test_exact_duplicate_scores_very_strong(self):
        """Exact match on price, mileage, seller, year, power, transmission, colour → VERY_STRONG."""
        result = self._dd.score_listing_pair(self.lid_a1, self.lid_p1, conn=self._conn)
        self.assertEqual(result["classification"], "VERY_STRONG",
                         f"Expected VERY_STRONG, got {result['classification']} (score={result['score']})")
        self.assertGreaterEqual(result["score"], 85)
        self.assertIn("exact price: €47.650", result["reasons"])
        self.assertIn("exact mileage: 19.500 km", result["reasons"])

    def test_same_model_different_mileage_scores_lower(self):
        """Same model+price but mileage 19500 vs 75000 → score well below VERY_STRONG."""
        result = self._dd.score_listing_pair(self.lid_a2, self.lid_p2, conn=self._conn)
        self.assertLess(result["score"], 85,
                        f"Different-mileage pair must not reach VERY_STRONG (score={result['score']})")
        self.assertTrue(
            any("mileage" in d.lower() for d in result["differences"]),
            "Mileage difference must appear in differences",
        )

    def test_same_title_different_seller_scores_lower(self):
        """Same title + price but clearly different sellers → reduced score."""
        result = self._dd.score_listing_pair(self.lid_a5, self.lid_p5, conn=self._conn)
        # Seller penalty fires; score should be below VERY_STRONG
        self.assertLess(result["score"], 85,
                        f"Different-seller pair must not reach VERY_STRONG (score={result['score']})")

    def test_conflicting_vin_never_strong(self):
        """Conflicting VINs must prevent STRONG/VERY_STRONG classification."""
        result = self._dd.score_listing_pair(self.lid_a3, self.lid_p3, conn=self._conn)
        self.assertIn(result["classification"], ("LOW", "POSSIBLE"),
                      f"Conflicting VIN must produce LOW/POSSIBLE (got {result['classification']})")
        self.assertTrue(
            any("conflicting VIN" in d for d in result["differences"]),
            "Conflicting VIN must appear in differences",
        )

    def test_same_source_listings_excluded_from_candidates(self):
        """Candidates from the same source (lid_a1 and lid_a4) must not appear."""
        summary = self._dd.run_detection(dry_run=True, conn=self._conn)
        same_source_pairs = [
            c for c in summary["top_candidates"]
            if {c["listing_id_a"], c["listing_id_b"]} == {self.lid_a1, self.lid_a4}
        ]
        self.assertEqual(len(same_source_pairs), 0,
                         "Same-source listings must not be paired")

    def test_candidate_persistence_is_idempotent(self):
        """Running detection twice must not create duplicate candidate rows."""
        self._dd.run_detection(dry_run=False, conn=self._conn)
        count_after_first = self._conn.execute(
            "SELECT COUNT(*) FROM listing_duplicate_candidates"
        ).fetchone()[0]

        self._dd.run_detection(dry_run=False, conn=self._conn)
        count_after_second = self._conn.execute(
            "SELECT COUNT(*) FROM listing_duplicate_candidates"
        ).fetchone()[0]

        self.assertEqual(count_after_first, count_after_second,
                         "Repeated detection must not insert duplicate rows")

    def test_evidence_is_stored(self):
        """After detection, evidence for the exact-match pair must be persisted."""
        self._dd.run_detection(dry_run=False, conn=self._conn)
        a, b = min(self.lid_a1, self.lid_p1), max(self.lid_a1, self.lid_p1)
        row = self._conn.execute(
            "SELECT evidence, classification FROM listing_duplicate_candidates WHERE listing_id_a=? AND listing_id_b=?",
            (a, b),
        ).fetchone()
        self.assertIsNotNone(row, "Exact-match pair must be persisted")
        import json as _json
        evidence = _json.loads(row[0])
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)
        self.assertEqual(row[1], "VERY_STRONG")

    def test_operator_status_preserved_on_rescore(self):
        """All human review fields must survive a rescore."""
        self._dd.run_detection(dry_run=False, conn=self._conn)
        a, b = min(self.lid_a1, self.lid_p1), max(self.lid_a1, self.lid_p1)
        for status in (
            "CONFIRMED_SAME", "CONFIRMED_DIFFERENT", "UNSURE", "DISMISSED"
        ):
            with self.subTest(status=status):
                comment = f"operator ground truth: {status}"
                self._conn.execute(
                    """
                    UPDATE listing_duplicate_candidates
                    SET status=?, operator_comment=?, reviewed_at=?
                    WHERE listing_id_a=? AND listing_id_b=?
                    """,
                    (status, comment, "2026-08-15T10:00:00", a, b),
                )
                self._conn.commit()

                self._dd.run_detection(dry_run=False, conn=self._conn)

                row = self._conn.execute(
                    """
                    SELECT status, operator_comment, reviewed_at
                    FROM listing_duplicate_candidates
                    WHERE listing_id_a=? AND listing_id_b=?
                    """,
                    (a, b),
                ).fetchone()
                self.assertEqual(
                    row[0], status,
                    "Operator status must not be overwritten on rescore",
                )
                self.assertEqual(row[1], comment)
                self.assertEqual(row[2], "2026-08-15T10:00:00")

    def test_no_vehicle_merge_occurs(self):
        """Detection must never set vehicle_id on any listing."""
        self._dd.run_detection(dry_run=False, conn=self._conn)
        rows = self._conn.execute(
            "SELECT COUNT(*) FROM listings WHERE vehicle_id IS NOT NULL"
        ).fetchone()[0]
        self.assertEqual(rows, 0, "Detection must not create any vehicle links")

    def test_dry_run_does_not_write_candidates(self):
        """dry_run=True must not persist anything."""
        self._dd.run_detection(dry_run=True, conn=self._conn)
        count = self._conn.execute(
            "SELECT COUNT(*) FROM listing_duplicate_candidates"
        ).fetchone()[0]
        self.assertEqual(count, 0, "dry_run must not write candidate rows")

    def test_score_pair_includes_required_keys(self):
        """score_pair result must always contain score, classification, reasons, differences."""
        result = self._dd.score_pair(
            {"id": 1, "price": 30000, "mileage": 50000, "seller": "Test Dealer", "year": "2022"},
            {"id": 2, "price": 30000, "mileage": 50000, "seller": "Test Dealer", "year": "2022"},
        )
        for key in ("score", "classification", "reasons", "differences"):
            self.assertIn(key, result, f"Missing key: {key}")
        self.assertIn(result["classification"],
                      ("LOW", "POSSIBLE", "STRONG", "VERY_STRONG"))
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_conflicting_vin_hard_veto_even_with_all_signals(self):
        """
        Even when every other signal matches perfectly, conflicting VINs must
        produce LOW or POSSIBLE — never STRONG or VERY_STRONG.
        This is the hard VIN veto rule.
        """
        perfect_match = {
            "id": 1, "price": 47650, "mileage": 19500,
            "seller": "Autocenter Neuss GmbH", "year": "2024",
            "title": "Audi A5 45 TFSI", "power_hp": 265,
            "drivetrain": "AWD", "transmission": "Automatik",
            "colour": "grau",
        }
        a = {**perfect_match, "vin": "WAUZZZ8T0PA000001"}
        b = {**perfect_match, "vin": "WAUZZZ8T0PA999999"}
        result = self._dd.score_pair(a, b)
        self.assertIn(
            result["classification"], ("LOW", "POSSIBLE"),
            f"Conflicting VIN must veto STRONG/VERY_STRONG even with all other signals matching "
            f"(got {result['classification']}, score={result['score']})",
        )
        self.assertNotIn(result["classification"], ("STRONG", "VERY_STRONG"))

    def test_snapshot_mutable_fields_not_used(self):
        """
        price, mileage, seller from listings table must override snapshot values.
        If a historical snapshot has a different price/mileage, the listings
        columns (current state) must win.
        """
        import json as _json
        # Add a listing where snapshot has stale price/mileage
        sl_stale = self._add_source_listing(
            self.sid_as24, "as24-stale-snap",
            "https://www.autoscout24.de/angebote/as24-stale-snap",
        )
        # Snapshot has OLD price 40000 / OLD mileage 10000
        self._add_snapshot(self.sid_as24, "as24-stale-snap", {
            "title": "Audi A5 40 TFSI", "price": 40000, "km": 10000,
            "year": 2021, "seller_name": "Old Dealer",
        })
        snap_id = self._conn.execute(
            "SELECT id FROM source_snapshots WHERE source_id=? AND source_listing_id=?",
            (self.sid_as24, "as24-stale-snap"),
        ).fetchone()[0]
        # But listings.current_price = 44000, current_mileage = 55000 (updated after rescrape)
        lid_stale = self._add_listing(
            self.sid_as24, "as24-stale-snap", sl_stale, snap_id,
            44000, 55000, "Current Dealer",
        )
        self._conn.commit()

        # Build listing data and confirm mutable fields come from listings columns
        snap = self._dd._get_snapshot_fields(lid_stale, self._conn)
        row = self._conn.execute(
            "SELECT id, source_id, source_listing_id, current_price, current_mileage, "
            "current_seller, current_description, current_options FROM listings WHERE id=?",
            (lid_stale,),
        ).fetchone()
        data = self._dd._listing_data(row, snap)

        self.assertEqual(data["price"], 44000,
                         "price must come from listings.current_price, not snapshot")
        self.assertEqual(data["mileage"], 55000,
                         "mileage must come from listings.current_mileage, not snapshot")
        self.assertEqual(data["seller"], "Current Dealer",
                         "seller must come from listings.current_seller, not snapshot")
        # Snapshot-enriched stable field should still work
        self.assertEqual(data["title"], "Audi A5 40 TFSI",
                         "stable title from snapshot must still be available")

    def test_stale_lifecycle_open_rows_marked_stale(self):
        """
        OPEN candidate rows that do not appear in a subsequent detection run
        must be marked STALE.  CONFIRMED/DISMISSED rows must be preserved.
        """
        # First run: persist candidates normally
        self._dd.run_detection(dry_run=False, conn=self._conn)

        # Manually mark the exact-match pair as CONFIRMED_SAME
        a, b = min(self.lid_a1, self.lid_p1), max(self.lid_a1, self.lid_p1)
        self._conn.execute(
            "UPDATE listing_duplicate_candidates SET status='CONFIRMED_SAME' WHERE listing_id_a=? AND listing_id_b=?",
            (a, b),
        )
        self._conn.commit()

        # Now make the a1/p1 pair fall out of the blocking window by updating mileage
        # so they differ by far more than 5%
        self._conn.execute(
            "UPDATE listings SET current_mileage=200000 WHERE id=?",
            (self.lid_p1,),
        )
        self._conn.commit()

        # Second run: exact-match pair no longer passes blocking
        self._dd.run_detection(dry_run=False, conn=self._conn)

        # CONFIRMED_SAME must still be CONFIRMED_SAME (not STALE)
        row = self._conn.execute(
            "SELECT status FROM listing_duplicate_candidates WHERE listing_id_a=? AND listing_id_b=?",
            (a, b),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "CONFIRMED_SAME",
                         "CONFIRMED_SAME must not be changed to STALE")

        # Check that a pair that was OPEN and is no longer in blocking is now STALE
        # (pick the a2/p2 pair which has very different mileage and was never confirmed)
        # Make a2/p2 pass blocking in first run by tweaking prices slightly different
        # Actually: we need an OPEN row that was NOT re-evaluated.
        # Insert a fake OPEN pair with non-existent listing IDs > real ones:
        self._conn.execute(
            """INSERT INTO listing_duplicate_candidates
               (listing_id_a, listing_id_b, score, classification, evidence, differences,
                status, last_evaluated_at, created_at, updated_at)
               VALUES (1,999,50,'POSSIBLE','[]','[]','OPEN',datetime('now','-1 day'),
                       datetime('now','-1 day'),datetime('now','-1 day'))""",
        )
        self._conn.commit()
        # Third run: this fake pair (1,999) is never generated by real blocking
        self._dd.run_detection(dry_run=False, conn=self._conn)
        row_stale = self._conn.execute(
            "SELECT status FROM listing_duplicate_candidates WHERE listing_id_a=1 AND listing_id_b=999"
        ).fetchone()
        self.assertIsNotNone(row_stale)
        self.assertEqual(row_stale[0], "STALE",
                         "OPEN rows not seen in latest run must be marked STALE")

    def test_stale_row_revived_when_pair_reappears(self):
        """
        A STALE candidate must revert to OPEN when the pair appears again in
        a subsequent detection run.
        """
        # Manually insert a STALE row for the exact-match pair
        a, b = min(self.lid_a1, self.lid_p1), max(self.lid_a1, self.lid_p1)
        self._conn.execute(
            """INSERT INTO listing_duplicate_candidates
               (listing_id_a, listing_id_b, score, classification, evidence, differences,
                status, last_evaluated_at, created_at, updated_at)
               VALUES (?,?,0,'LOW','[]','[]','STALE',datetime('now','-1 day'),
                       datetime('now','-1 day'),datetime('now','-1 day'))""",
            (a, b),
        )
        self._conn.commit()

        # Run detection: the real pair passes blocking and gets rescored → STALE → OPEN
        self._dd.run_detection(dry_run=False, conn=self._conn)

        row = self._conn.execute(
            "SELECT status, classification FROM listing_duplicate_candidates WHERE listing_id_a=? AND listing_id_b=?",
            (a, b),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "OPEN",
                         "Revived STALE pair must return to OPEN")
        self.assertEqual(row[1], "VERY_STRONG",
                         "Revived pair must be correctly rescored")



class TestDuplicateReviewPortal(unittest.TestCase):
    """
    Tests for the duplicate-review portal DB helpers in duplicate_detection.py.
    Uses isolated temporary databases — no live inventory dependency.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.orig_db = config.DATABASE
        config.DATABASE = os.path.join(self.tempdir.name, "portal_test.db")
        database.get_connection().close()
        import duplicate_detection as _dd
        self._dd = _dd
        self._conn = database.get_connection()
        _dd.ensure_schema(self._conn)
        self._conn.commit()
        self._populate_fixtures()

    def tearDown(self):
        self._conn.close()
        config.DATABASE = self.orig_db
        self.tempdir.cleanup()

    # ── fixture helpers (same pattern as TestDuplicateDetection) ──────────

    def _add_source(self, name, display_name=None):
        self._conn.execute(
            "INSERT OR IGNORE INTO sources (source_name, display_name) VALUES (?,?)",
            (name, display_name or name),
        )
        return self._conn.execute(
            "SELECT id FROM sources WHERE source_name=?", (name,)
        ).fetchone()[0]

    def _add_source_listing(self, source_id, listing_id, url):
        self._conn.execute(
            "INSERT INTO source_listings (source_id, source_listing_id, source_url) VALUES (?,?,?)",
            (source_id, listing_id, url),
        )
        return self._conn.execute(
            "SELECT id FROM source_listings WHERE source_id=? AND source_listing_id=?",
            (source_id, listing_id),
        ).fetchone()[0]

    def _add_snapshot(self, source_id, listing_id, fields):
        import json as _json
        sl_row = self._conn.execute(
            "SELECT id FROM source_listings WHERE source_id=? AND source_listing_id=?",
            (source_id, listing_id),
        ).fetchone()
        self._conn.execute(
            """INSERT OR IGNORE INTO source_snapshots
               (source_id, source_listing_id, snapshot_hash, extracted_fields,
                discovered_at, fetched_at)
               VALUES (?,?,?,?,datetime('now'),datetime('now'))""",
            (source_id, listing_id, f"h-{listing_id}", _json.dumps(fields)),
        )
        return self._conn.execute(
            "SELECT id FROM source_snapshots WHERE source_id=? AND source_listing_id=?",
            (source_id, listing_id),
        ).fetchone()[0]

    def _add_listing(self, source_id, source_listing_id, sl_row_id, snap_id,
                     price, mileage, seller):
        self._conn.execute(
            """INSERT INTO listings
               (source_id, source_listing_id, source_listing_row_id,
                current_price, current_mileage, current_seller,
                latest_source_snapshot_id, availability)
               VALUES (?,?,?,?,?,?,?,'ACTIVE')""",
            (source_id, source_listing_id, sl_row_id, price, mileage, seller, snap_id),
        )
        return self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _insert_candidate(self, lid_a, lid_b, score, classification, status="OPEN",
                          evidence=None, differences=None, comment=None, reviewed_at=None):
        import json as _json
        a, b = min(lid_a, lid_b), max(lid_a, lid_b)
        self._conn.execute(
            """INSERT INTO listing_duplicate_candidates
               (listing_id_a, listing_id_b, score, classification, evidence, differences,
                status, operator_comment, reviewed_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))""",
            (a, b, score, classification,
             _json.dumps(evidence or []), _json.dumps(differences or []),
             status, comment, reviewed_at),
        )
        self._conn.commit()
        return self._conn.execute(
            "SELECT id FROM listing_duplicate_candidates WHERE listing_id_a=? AND listing_id_b=?",
            (a, b),
        ).fetchone()[0]

    def _populate_fixtures(self):
        sid_as24 = self._add_source("autoscout24", "AutoScout24")
        sid_pkw  = self._add_source("pkw_de", "PKW.de")
        self.sid_as24 = sid_as24
        self.sid_pkw  = sid_pkw

        sl1 = self._add_source_listing(sid_as24, "as24-p1",
                                       "https://www.autoscout24.de/angebote/as24-p1")
        snap1 = self._add_snapshot(sid_as24, "as24-p1",
                                   {"title": "Audi A5 45 TFSI", "year": 2024})
        self.lid_a1 = self._add_listing(sid_as24, "as24-p1", sl1, snap1,
                                        47650, 19500, "Autocenter Neuss GmbH")

        sl2 = self._add_source_listing(sid_pkw, "pkw-p1",
                                       "https://suche.pkw.de/fahrzeuge/details/pkw-p1")
        snap2 = self._add_snapshot(sid_pkw, "pkw-p1",
                                   {"title": "Audi A5 Cabriolet 45 TFSI quattro S line",
                                    "year": 2024})
        self.lid_p1 = self._add_listing(sid_pkw, "pkw-p1", sl2, snap2,
                                        47650, 19500, "AUTOCENTER NEUSS GmbH")

        # Second cross-source pair (STRONG)
        sl3 = self._add_source_listing(sid_as24, "as24-p2",
                                       "https://www.autoscout24.de/angebote/as24-p2")
        snap3 = self._add_snapshot(sid_as24, "as24-p2",
                                   {"title": "Audi A5 2.0 TFSI", "year": 2022})
        self.lid_a2 = self._add_listing(sid_as24, "as24-p2", sl3, snap3,
                                        28000, 60000, "Autohaus Muster GmbH")

        sl4 = self._add_source_listing(sid_pkw, "pkw-p2",
                                       "https://suche.pkw.de/fahrzeuge/details/pkw-p2")
        snap4 = self._add_snapshot(sid_pkw, "pkw-p2",
                                   {"title": "Audi A5 2.0 TFSI quattro", "year": 2022})
        self.lid_p2 = self._add_listing(sid_pkw, "pkw-p2", sl4, snap4,
                                        28000, 60000, "Autohaus Muster")

        self._conn.commit()

        # Persist candidates
        self.cid_vs = self._insert_candidate(
            self.lid_a1, self.lid_p1, 93, "VERY_STRONG", "OPEN",
            evidence=["exact price: €47.650", "exact mileage: 19.500 km", "same seller: Autocenter Neuss"],
        )
        self.cid_strong = self._insert_candidate(
            self.lid_a2, self.lid_p2, 75, "STRONG", "OPEN",
            evidence=["exact price: €28.000", "exact mileage: 60.000 km"],
        )

    # ── Tests ──────────────────────────────────────────────────────────────

    def test_list_defaults_open_strong_very_strong(self):
        """Default list must return OPEN VERY_STRONG and STRONG, not LOW."""
        # Insert a LOW candidate
        self._insert_candidate(self.lid_a1, self.lid_p2, 20, "LOW", "OPEN")
        candidates = self._dd.get_duplicate_candidates(conn=self._conn)
        classifications = {c["classification"] for c in candidates}
        self.assertIn("VERY_STRONG", classifications)
        self.assertIn("STRONG", classifications)
        self.assertNotIn("LOW", classifications,
                         "LOW candidates must be excluded from default list")

    def test_list_excludes_stale_by_default(self):
        """Default list (status=None → OPEN only) must exclude STALE rows."""
        self._insert_candidate(self.lid_a1, self.lid_p2, 80, "STRONG", "STALE")
        candidates = self._dd.get_duplicate_candidates(conn=self._conn)
        statuses = {c["status"] for c in candidates}
        self.assertNotIn("STALE", statuses,
                         "STALE candidates must not appear in the default queue")

    def test_list_sorted_very_strong_first(self):
        """VERY_STRONG must appear before STRONG in default list."""
        candidates = self._dd.get_duplicate_candidates(conn=self._conn)
        self.assertGreater(len(candidates), 1)
        self.assertEqual(candidates[0]["classification"], "VERY_STRONG",
                         "VERY_STRONG must be first in sorted list")

    def test_candidate_detail_includes_both_source_labels(self):
        """Detail must contain source_label for both listings."""
        detail = self._dd.get_duplicate_candidate(self.cid_vs, conn=self._conn)
        self.assertIsNotNone(detail)
        label_a = detail["listing_a"]["source_label"]
        label_b = detail["listing_b"]["source_label"]
        # Neither label must be empty/generic
        self.assertTrue(label_a, "source_label for listing_a must not be empty")
        self.assertTrue(label_b, "source_label for listing_b must not be empty")
        # Labels must be different (different sources)
        self.assertNotEqual(label_a, label_b,
                            "Two different sources must have different labels")

    def test_autoscout24_url_in_detail(self):
        """AutoScout24 listing must expose its original URL."""
        detail = self._dd.get_duplicate_candidate(self.cid_vs, conn=self._conn)
        as24_side = (
            detail["listing_a"] if detail["listing_a"]["source_label"] == "AutoScout24"
            else detail["listing_b"]
        )
        self.assertIn("autoscout24.de", as24_side["source_url"],
                      "AutoScout24 URL must point to autoscout24.de")

    def test_pkwde_url_in_detail(self):
        """PKW.de listing must expose its original URL."""
        detail = self._dd.get_duplicate_candidate(self.cid_vs, conn=self._conn)
        pkw_side = (
            detail["listing_a"] if "pkw" in detail["listing_a"]["source_label"].lower()
            else detail["listing_b"]
        )
        self.assertIn("pkw.de", pkw_side["source_url"],
                      "PKW.de URL must point to pkw.de")

    def test_source_label_not_hardcoded(self):
        """source_label must come from sources.display_name, not hardcoded strings."""
        # Add a new generic source
        sid_new = self._add_source("test_source_xyz", "TestSource XYZ")
        sl = self._add_source_listing(sid_new, "xyz-1", "https://test.example.com/1")
        snap = self._add_snapshot(sid_new, "xyz-1", {"title": "Test Car"})
        lid_new = self._add_listing(sid_new, "xyz-1", sl, snap, 47650, 19500, "Test Dealer")
        self._conn.commit()

        a, b = min(self.lid_a1, lid_new), max(self.lid_a1, lid_new)
        cid = self._insert_candidate(a, b, 80, "STRONG")
        detail = self._dd.get_duplicate_candidate(cid, conn=self._conn)
        labels = {detail["listing_a"]["source_label"], detail["listing_b"]["source_label"]}
        self.assertIn("TestSource XYZ", labels,
                      "source_label must reflect sources.display_name for any source")

    def test_review_confirmed_same_persists(self):
        """CONFIRMED_SAME must be stored with reviewed_at timestamp."""
        self._dd.update_duplicate_candidate_review(
            self.cid_vs,
            status="CONFIRMED_SAME",
            operator_comment="Exact match on all fields",
            conn=self._conn,
        )
        row = self._conn.execute(
            "SELECT status, operator_comment, reviewed_at FROM listing_duplicate_candidates WHERE id=?",
            (self.cid_vs,),
        ).fetchone()
        self.assertEqual(row[0], "CONFIRMED_SAME")
        self.assertEqual(row[1], "Exact match on all fields")
        self.assertIsNotNone(row[2], "reviewed_at must be set")

    def test_review_confirmed_different_persists(self):
        """CONFIRMED_DIFFERENT must be stored."""
        self._dd.update_duplicate_candidate_review(
            self.cid_vs, status="CONFIRMED_DIFFERENT",
            operator_comment="Different colour", conn=self._conn,
        )
        row = self._conn.execute(
            "SELECT status FROM listing_duplicate_candidates WHERE id=?", (self.cid_vs,)
        ).fetchone()
        self.assertEqual(row[0], "CONFIRMED_DIFFERENT")

    def test_review_unsure_persists(self):
        """UNSURE status must be stored."""
        self._dd.update_duplicate_candidate_review(
            self.cid_vs, status="UNSURE",
            operator_comment="Cannot determine from available info", conn=self._conn,
        )
        row = self._conn.execute(
            "SELECT status FROM listing_duplicate_candidates WHERE id=?", (self.cid_vs,)
        ).fetchone()
        self.assertEqual(row[0], "UNSURE")

    def test_comment_persists(self):
        """operator_comment must be stored exactly as entered."""
        comment = "Dealer phones match, exact mileage, same options list"
        self._dd.update_duplicate_candidate_review(
            self.cid_vs, status="CONFIRMED_SAME",
            operator_comment=comment, conn=self._conn,
        )
        row = self._conn.execute(
            "SELECT operator_comment FROM listing_duplicate_candidates WHERE id=?", (self.cid_vs,)
        ).fetchone()
        self.assertEqual(row[0], comment)

    def test_reviewed_at_is_set(self):
        """reviewed_at must be populated on review."""
        self._dd.update_duplicate_candidate_review(
            self.cid_vs, status="CONFIRMED_SAME", conn=self._conn,
        )
        row = self._conn.execute(
            "SELECT reviewed_at FROM listing_duplicate_candidates WHERE id=?", (self.cid_vs,)
        ).fetchone()
        self.assertIsNotNone(row[0])
        # Must be a parseable timestamp
        from datetime import datetime as _dt
        _dt.fromisoformat(row[0])

    def test_review_does_not_change_vehicle_id(self):
        """Reviewing a candidate must never set vehicle_id on any listing."""
        self._dd.update_duplicate_candidate_review(
            self.cid_vs, status="CONFIRMED_SAME",
            operator_comment="Confirmed", conn=self._conn,
        )
        rows = self._conn.execute(
            "SELECT COUNT(*) FROM listings WHERE vehicle_id IS NOT NULL"
        ).fetchone()[0]
        self.assertEqual(rows, 0, "Review must never set vehicle_id")

    def test_review_status_survives_detector_rescore(self):
        """Operator decision must survive a full detection rescore."""
        self._dd.update_duplicate_candidate_review(
            self.cid_vs, status="CONFIRMED_SAME",
            operator_comment="Confirmed by human", conn=self._conn,
        )
        # Rescore via run_detection
        self._dd.run_detection(dry_run=False, conn=self._conn)
        row = self._conn.execute(
            "SELECT status, operator_comment FROM listing_duplicate_candidates WHERE id=?",
            (self.cid_vs,),
        ).fetchone()
        self.assertEqual(row[0], "CONFIRMED_SAME",
                         "Operator decision must survive detector rescore")
        self.assertEqual(row[1], "Confirmed by human")

    def test_next_open_navigation(self):
        """get_next_open_candidate must return the next OPEN candidate after current."""
        # cid_vs is VERY_STRONG, cid_strong is STRONG — after confirming vs, next = strong
        self._dd.update_duplicate_candidate_review(
            self.cid_vs, status="CONFIRMED_SAME", conn=self._conn,
        )
        # cid_vs is now CONFIRMED_SAME, not OPEN — next open from queue top
        next_id = self._dd.get_next_open_candidate(conn=self._conn)
        self.assertEqual(next_id, self.cid_strong,
                         "Next open after review must point to next OPEN candidate")

    def test_next_open_returns_none_when_queue_empty(self):
        """get_next_open_candidate must return None when all reviewable candidates are reviewed."""
        for cid in [self.cid_vs, self.cid_strong]:
            self._dd.update_duplicate_candidate_review(
                cid, status="CONFIRMED_SAME", conn=self._conn,
            )
        result = self._dd.get_next_open_candidate(conn=self._conn)
        self.assertIsNone(result, "Empty review queue must return None")

    def test_review_summary_counts(self):
        """get_review_summary must return correct counts."""
        self._dd.update_duplicate_candidate_review(
            self.cid_vs, status="CONFIRMED_SAME", conn=self._conn,
        )
        summary = self._dd.get_review_summary(conn=self._conn)
        self.assertEqual(summary.get("CONFIRMED_SAME", 0), 1)
        self.assertEqual(summary.get("OPEN", 0), 1)

    def test_webapp_duplicates_list_route(self):
        """GET /duplicates must return 200 with candidate data."""
        import webapp
        with webapp.app.test_client() as client:
            resp = client.get("/duplicates")
        self.assertEqual(resp.status_code, 200)
        body = resp.data.decode()
        self.assertIn("Duplicate Review", body)

    def test_webapp_duplicates_detail_route(self):
        """GET /duplicates/<id> must return 200 with source labels."""
        import webapp
        # Run detection to create real candidates in the portal test DB
        self._dd.run_detection(dry_run=False, conn=self._conn)
        a, b = min(self.lid_a1, self.lid_p1), max(self.lid_a1, self.lid_p1)
        cid = self._conn.execute(
            "SELECT id FROM listing_duplicate_candidates WHERE listing_id_a=? AND listing_id_b=?",
            (a, b),
        ).fetchone()[0]
        with webapp.app.test_client() as client:
            resp = client.get(f"/duplicates/{cid}")
        self.assertEqual(resp.status_code, 200)
        body = resp.data.decode()
        self.assertIn("AutoScout24", body)
        self.assertIn("PKW.de", body)

    def test_webapp_duplicates_detail_404(self):
        """GET /duplicates/99999 must return 404."""
        import webapp
        with webapp.app.test_client() as client:
            resp = client.get("/duplicates/99999")
        self.assertEqual(resp.status_code, 404)

    def test_webapp_review_post_persists(self):
        """POST /duplicates/<id>/review must persist status and redirect."""
        import webapp
        with webapp.app.test_client() as client:
            resp = client.post(
                f"/duplicates/{self.cid_vs}/review",
                data={"status": "CONFIRMED_SAME",
                      "operator_comment": "Confirmed by test"},
                follow_redirects=False,
            )
        self.assertIn(resp.status_code, (302, 303),
                      "Review POST must redirect")
        row = self._conn.execute(
            "SELECT status, operator_comment FROM listing_duplicate_candidates WHERE id=?",
            (self.cid_vs,),
        ).fetchone()
        self.assertEqual(row[0], "CONFIRMED_SAME")
        self.assertEqual(row[1], "Confirmed by test")

    def test_invalid_review_status_rejected(self):
        """POST with an unsupported status value must return 400."""
        import webapp
        with webapp.app.test_client() as client:
            resp = client.post(
                f"/duplicates/{self.cid_vs}/review",
                data={"status": "MERGE_NOW"},
                follow_redirects=False,
            )
        self.assertEqual(resp.status_code, 400,
                         "Invalid status must be rejected with 400")
        # Row must be unchanged
        row = self._conn.execute(
            "SELECT status FROM listing_duplicate_candidates WHERE id=?", (self.cid_vs,)
        ).fetchone()
        self.assertEqual(row[0], "OPEN", "Status must not change on invalid POST")

    def test_review_modifies_no_vehicle_or_listing_identity(self):
        """Review POST must not touch listings, vehicles, source_listings, or cars."""
        import webapp
        # Record baseline counts
        before_listings = self._conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        before_sources  = self._conn.execute("SELECT COUNT(*) FROM source_listings").fetchone()[0]

        with webapp.app.test_client() as client:
            client.post(
                f"/duplicates/{self.cid_vs}/review",
                data={"status": "CONFIRMED_SAME", "operator_comment": "test"},
                follow_redirects=False,
            )

        after_listings = self._conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        after_sources  = self._conn.execute("SELECT COUNT(*) FROM source_listings").fetchone()[0]
        vehicle_ids    = self._conn.execute(
            "SELECT COUNT(*) FROM listings WHERE vehicle_id IS NOT NULL"
        ).fetchone()[0]

        self.assertEqual(before_listings, after_listings, "listings count must not change")
        self.assertEqual(before_sources,  after_sources,  "source_listings count must not change")
        self.assertEqual(vehicle_ids, 0, "vehicle_id must remain NULL after review")


class TestDuplicateSchemaMigration(unittest.TestCase):
    """
    Tests that verify ensure_schema() correctly migrates databases that were
    created with the old (incomplete) CHECK constraint.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.orig_db = config.DATABASE
        config.DATABASE = os.path.join(self.tempdir.name, "migration_test.db")
        database.get_connection().close()
        import duplicate_detection as _dd
        self._dd = _dd
        self._conn = database.get_connection()

    def tearDown(self):
        self._conn.close()
        config.DATABASE = self.orig_db
        self.tempdir.cleanup()

    def _create_old_schema(self):
        """Create the original v1 schema without STALE/UNSURE and without new columns."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS listing_duplicate_candidates (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id_a      INTEGER NOT NULL,
                listing_id_b      INTEGER NOT NULL,
                score             INTEGER NOT NULL,
                classification    TEXT NOT NULL,
                evidence          TEXT NOT NULL DEFAULT '[]',
                differences       TEXT NOT NULL DEFAULT '[]',
                status            TEXT NOT NULL DEFAULT 'OPEN',
                created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(listing_id_a, listing_id_b),
                CHECK (listing_id_a < listing_id_b),
                CHECK (status IN ('OPEN','CONFIRMED_SAME','CONFIRMED_DIFFERENT','DISMISSED'))
            );
        """)
        self._conn.commit()

    def _insert_old_row(self, lid_a, lid_b, score, classification, status="OPEN",
                        comment=None):
        """Insert a row compatible with the old schema."""
        import json as _json
        a, b = min(lid_a, lid_b), max(lid_a, lid_b)
        self._conn.execute(
            """INSERT INTO listing_duplicate_candidates
               (listing_id_a, listing_id_b, score, classification, evidence, differences,
                status, created_at, updated_at)
               VALUES (?,?,?,?,'[]','[]',?,datetime('now'),datetime('now'))""",
            (a, b, score, classification, status),
        )
        self._conn.commit()
        return self._conn.execute(
            "SELECT id FROM listing_duplicate_candidates WHERE listing_id_a=? AND listing_id_b=?",
            (a, b),
        ).fetchone()[0]

    def test_migration_adds_new_columns(self):
        """ensure_schema must add last_evaluated_at, operator_comment, reviewed_at."""
        self._create_old_schema()
        self._dd.ensure_schema(self._conn)
        cols = {r[1] for r in self._conn.execute(
            "PRAGMA table_info(listing_duplicate_candidates)"
        ).fetchall()}
        self.assertIn("last_evaluated_at", cols)
        self.assertIn("operator_comment", cols)
        self.assertIn("reviewed_at", cols)

    def test_migration_enables_unsure_status(self):
        """After migration, UNSURE must be accepted by the CHECK constraint."""
        self._create_old_schema()
        cid = self._insert_old_row(1, 2, 80, "STRONG", "OPEN")
        self._dd.ensure_schema(self._conn)
        self._conn.commit()
        # Should not raise
        self._conn.execute(
            "UPDATE listing_duplicate_candidates SET status='UNSURE' WHERE id=?", (cid,)
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT status FROM listing_duplicate_candidates WHERE id=?", (cid,)
        ).fetchone()
        self.assertEqual(row[0], "UNSURE",
                         "UNSURE must be accepted after migration")

    def test_migration_enables_stale_status(self):
        """After migration, STALE must be accepted by the CHECK constraint."""
        self._create_old_schema()
        cid = self._insert_old_row(1, 2, 80, "STRONG", "OPEN")
        self._dd.ensure_schema(self._conn)
        self._conn.commit()
        self._conn.execute(
            "UPDATE listing_duplicate_candidates SET status='STALE' WHERE id=?", (cid,)
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT status FROM listing_duplicate_candidates WHERE id=?", (cid,)
        ).fetchone()
        self.assertEqual(row[0], "STALE",
                         "STALE must be accepted after migration")

    def test_existing_rows_survive_migration(self):
        """All rows (including operator decisions) must survive reconstruction."""
        self._create_old_schema()
        self._insert_old_row(1, 2, 93, "VERY_STRONG", "CONFIRMED_SAME")
        self._insert_old_row(3, 4, 75, "STRONG", "OPEN")
        self._insert_old_row(5, 6, 50, "POSSIBLE", "CONFIRMED_DIFFERENT")
        self._dd.ensure_schema(self._conn)
        self._conn.commit()
        rows = self._conn.execute(
            "SELECT listing_id_a, listing_id_b, score, classification, status "
            "FROM listing_duplicate_candidates ORDER BY listing_id_a"
        ).fetchall()
        self.assertEqual(len(rows), 3, "Row count must be preserved after migration")
        self.assertEqual(rows[0], (1, 2, 93, "VERY_STRONG", "CONFIRMED_SAME"))
        self.assertEqual(rows[1], (3, 4, 75, "STRONG", "OPEN"))
        self.assertEqual(rows[2], (5, 6, 50, "POSSIBLE", "CONFIRMED_DIFFERENT"))

    def test_human_review_survives_migration(self):
        """operator_comment and reviewed_at (if present pre-migration) must be preserved."""
        self._create_old_schema()
        # First run the column migrations so reviewed_at exists before we write to it
        for m in self._dd._MIGRATIONS:
            try:
                self._conn.execute(m)
            except Exception:
                pass
        self._conn.commit()
        cid = self._insert_old_row(1, 2, 90, "VERY_STRONG", "CONFIRMED_SAME")
        self._conn.execute(
            "UPDATE listing_duplicate_candidates SET operator_comment=?, reviewed_at=? WHERE id=?",
            ("Same dealer confirmed by phone", "2026-08-14T20:00:00", cid),
        )
        self._conn.commit()
        # Now run full ensure_schema (which includes reconstruction)
        self._dd.ensure_schema(self._conn)
        self._conn.commit()
        row = self._conn.execute(
            "SELECT status, operator_comment, reviewed_at FROM listing_duplicate_candidates WHERE id=?",
            (cid,),
        ).fetchone()
        self.assertEqual(row[0], "CONFIRMED_SAME")
        self.assertEqual(row[1], "Same dealer confirmed by phone")
        self.assertEqual(row[2], "2026-08-14T20:00:00")

    def test_ensure_schema_idempotent(self):
        """Calling ensure_schema twice must produce no error and no data change."""
        self._create_old_schema()
        self._insert_old_row(1, 2, 85, "VERY_STRONG", "OPEN")
        self._dd.ensure_schema(self._conn)
        self._conn.commit()
        self._dd.ensure_schema(self._conn)
        self._conn.commit()
        cnt = self._conn.execute(
            "SELECT COUNT(*) FROM listing_duplicate_candidates"
        ).fetchone()[0]
        self.assertEqual(cnt, 1, "Row count must be 1 after two ensure_schema calls")
        sql = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='listing_duplicate_candidates'"
        ).fetchone()[0]
        self.assertIn(self._dd._REQUIRED_CHECK, sql,
                      "CHECK constraint must be correct after second ensure_schema")

    def test_fresh_schema_has_no_old_constraint(self):
        """A freshly created table must have the full CHECK constraint from _DDL."""
        # Do NOT call _create_old_schema — let ensure_schema create it fresh
        self._dd.ensure_schema(self._conn)
        sql = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='listing_duplicate_candidates'"
        ).fetchone()[0]
        self.assertIn(self._dd._REQUIRED_CHECK, sql,
                      "Fresh schema must include STALE and UNSURE in CHECK constraint")

    def test_next_open_no_wraparound_after_last(self):
        """get_next_open_candidate called after the last candidate must return None,
        not wrap to the first."""
        # Create a source + two listings + two OPEN candidates
        self._conn.executescript("""
            INSERT OR IGNORE INTO sources (source_name, display_name) VALUES ('src_a','Source A');
            INSERT OR IGNORE INTO sources (source_name, display_name) VALUES ('src_b','Source B');
        """)
        sid_a = self._conn.execute("SELECT id FROM sources WHERE source_name='src_a'").fetchone()[0]
        sid_b = self._conn.execute("SELECT id FROM sources WHERE source_name='src_b'").fetchone()[0]
        for sl_id, url in [("x1","https://a.com/1"),("x2","https://a.com/2")]:
            self._conn.execute(
                "INSERT INTO source_listings (source_id, source_listing_id, source_url) VALUES (?,?,?)",
                (sid_a, sl_id, url),
            )
        for sl_id, url in [("y1","https://b.com/1"),("y2","https://b.com/2")]:
            self._conn.execute(
                "INSERT INTO source_listings (source_id, source_listing_id, source_url) VALUES (?,?,?)",
                (sid_b, sl_id, url),
            )
        # listings table requires source_listing_row_id; skip snapshot for simplicity
        for i, (sid, sl_id, price, km) in enumerate([
            (sid_a, "x1", 30000, 50000),
            (sid_b, "y1", 30000, 50000),
        ], 1):
            sl_row = self._conn.execute(
                "SELECT id FROM source_listings WHERE source_id=? AND source_listing_id=?",
                (sid, sl_id),
            ).fetchone()[0]
            self._conn.execute(
                """INSERT INTO listings (source_id, source_listing_id, source_listing_row_id,
                   current_price, current_mileage, availability)
                   VALUES (?,?,?,?,?,'ACTIVE')""",
                (sid, sl_id, sl_row, price, km),
            )
        lids = [r[0] for r in self._conn.execute("SELECT id FROM listings ORDER BY id").fetchall()]
        self._conn.commit()
        self._dd.ensure_schema(self._conn)
        self._conn.commit()
        # Insert one OPEN candidate
        a, b = min(lids[0], lids[1]), max(lids[0], lids[1])
        self._conn.execute(
            """INSERT INTO listing_duplicate_candidates
               (listing_id_a, listing_id_b, score, classification, evidence, differences,
                status, created_at, updated_at)
               VALUES (?,?,85,'VERY_STRONG','[]','[]','OPEN',datetime('now'),datetime('now'))""",
            (a, b),
        )
        self._conn.commit()
        cid = self._conn.execute(
            "SELECT id FROM listing_duplicate_candidates WHERE listing_id_a=? AND listing_id_b=?",
            (a, b),
        ).fetchone()[0]

        # First call: should return the one OPEN candidate
        next1 = self._dd.get_next_open_candidate(conn=self._conn)
        self.assertEqual(next1, cid)

        # After providing after_id=cid, no further OPEN candidates exist
        next2 = self._dd.get_next_open_candidate(after_id=cid, conn=self._conn)
        self.assertIsNone(next2,
                          "get_next_open_candidate must return None after the last OPEN candidate, "
                          "not wrap to the first")


class TestNormalization(unittest.TestCase):
    """
    Regression tests for semantic normalization helpers in duplicate_detection.py.
    All tests are pure unit tests — no database required.
    """

    def setUp(self):
        import duplicate_detection as _dd
        self._dd = _dd

    # ── Colour ────────────────────────────────────────────────────────────

    def _colour(self, s):
        return self._dd._norm_colour(s)

    def test_colour_de_nl_equivalents(self):
        """Common DE/NL/EN colour equivalents must normalise to the same canonical value."""
        pairs = [
            ("zilver", "silber"),   # NL vs DE
            ("grijs",  "grau"),     # NL vs DE
            ("zwart",  "schwarz"),  # NL vs DE
            ("rood",   "rot"),      # NL vs DE
            ("groen",  "grün"),     # NL vs DE
            ("wit",    "weiß"),     # NL vs DE
            ("wit",    "weiss"),    # NL vs DE alt
            ("blauw",  "blau"),     # NL vs DE
            ("bruin",  "braun"),    # NL vs DE
        ]
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                self.assertEqual(self._colour(a), self._colour(b),
                                 f"colour '{a}' and '{b}' must normalise to the same value")

    def test_colour_en_de_equivalents(self):
        """EN/DE colour equivalents."""
        pairs = [
            ("grey", "grau"), ("gray", "grau"), ("silver", "silber"),
            ("black", "schwarz"), ("white", "weiß"), ("blue", "blau"),
            ("red", "rot"), ("green", "grün"), ("brown", "braun"),
        ]
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                self.assertEqual(self._colour(a), self._colour(b))

    def test_colour_none_returns_empty(self):
        self.assertEqual(self._colour(None), "")
        self.assertEqual(self._colour(""), "")

    def test_colour_unknown_passthrough(self):
        """Unknown colour values must pass through unchanged (lowercased)."""
        self.assertEqual(self._colour("Champagner"), "champagner")

    # ── Seller ────────────────────────────────────────────────────────────

    def _seller(self, s):
        return self._dd._norm_seller(s)

    def _sim(self, a, b):
        return self._dd._token_similarity(
            self._dd._norm_seller(a), self._dd._norm_seller(b)
        )

    def test_seller_extracts_company_name_from_dict_repr(self):
        """_norm_seller must extract companyName from AS24 Python dict repr."""
        raw = "{'companyName': 'Autogalerie Remscheid', 'other': 'stuff'}"
        normed = self._seller(raw)
        # After normalisation the core name token must be present
        # (generic prefix "AUTOGALERIE" may be stripped; "REMSCHEID" must remain)
        self.assertIn("REMSCHEID", normed,
                      f"Core dealer name token must survive normalisation: {normed!r}")

    def test_seller_strips_legal_suffixes(self):
        """GmbH, KG, Co etc. must be removed."""
        self.assertNotIn("GMBH", self._seller("Autohaus Schmidt GmbH"))
        self.assertNotIn("KG",   self._seller("Autohaus Schmidt GmbH & Co. KG"))

    def test_seller_strips_dealer_prefix(self):
        """Generic dealer prefixes (Autohaus, Auto, …) must be stripped."""
        self.assertNotIn("AUTOHAUS", self._seller("Autohaus Schmidt"))
        self.assertNotIn("AUTO",     self._seller("Autocenter Neuss"))

    def test_seller_autohaus_prefix_match(self):
        """'Autohaus Schmidt' vs 'Schmidt' must score >= 0.70."""
        sim = self._sim("Autohaus Schmidt GmbH", "Schmidt")
        self.assertGreaterEqual(sim, 0.70,
                                f"'Autohaus Schmidt GmbH' vs 'Schmidt' sim={sim:.2f} must be >= 0.70")

    def test_seller_dannacker_case(self):
        """Dannacker & Laudien GmbH vs Autohaus Dannacker & Laudien GmbH & Co. KG."""
        a = "{'companyName': 'Dannacker & Laudien GmbH'}"
        b = "Autohaus Dannacker & Laudien GmbH & Co. KG"
        sim = self._sim(a, b)
        self.assertGreaterEqual(sim, 0.70,
                                f"Dannacker case sim={sim:.2f} must be >= 0.70")

    def test_seller_klann_case(self):
        """'Autohaus Klann GmbH' vs 'Autohaus Klann'."""
        a = "{'companyName': 'Autohaus Klann GmbH'}"
        b = "Autohaus Klann"
        sim = self._sim(a, b)
        self.assertEqual(sim, 1.0, f"Klann case sim={sim:.2f} must be 1.0")

    def test_seller_hyphen_space_variant(self):
        """'Nord-Automobile' vs 'Nord Automobile' must match."""
        a = "{'companyName': 'Nord-Automobile'}"
        b = "Nord Automobile"
        sim = self._sim(a, b)
        self.assertGreaterEqual(sim, 0.70,
                                f"Hyphen/space variant sim={sim:.2f} must be >= 0.70")

    def test_seller_clearly_different_stays_low(self):
        """Unrelated sellers must not score >= 0.70."""
        sim = self._sim("Autohaus München GmbH", "Fahrzeugcenter Hamburg AG")
        self.assertLess(sim, 0.70,
                        f"Clearly different sellers sim={sim:.2f} must be < 0.70")

    def test_seller_none_returns_empty(self):
        self.assertEqual(self._seller(None), "")
        self.assertEqual(self._seller(""), "")

    def test_seller_contact_name_matches_plain_seller(self):
        a = {
            "seller": (
                "{'companyName': 'Autohaus Eggers', "
                "'contactName': 'Yannick Hoppe'}"
            ),
        }
        b = {"seller": "Fahrzeugtechnik Yannick Hoppe"}
        result = self._dd.score_pair(a, b)
        self.assertIn("same seller contact: Yannick Hoppe", result["reasons"])

    def test_related_seller_companies_are_not_identical(self):
        result = self._dd.score_pair(
            {"seller": "Cosmo D&V GmbH"},
            {"seller": "Cosmo Gruppe"},
        )
        self.assertTrue(
            any(reason.startswith("related seller companies:") for reason in result["reasons"])
        )
        self.assertFalse(
            any(reason.startswith("same seller company:") for reason in result["reasons"])
        )

    def test_generic_automobile_token_does_not_relate_companies(self):
        result = self._dd.score_pair(
            {"seller": "Fischer Automobile GmbH & Co. KG"},
            {"seller": "Nord Automobile"},
        )
        self.assertTrue(
            any(diff.startswith("seller conflict:") for diff in result["differences"])
        )

    # ── Vehicle signature and contradictions ─────────────────────────────

    def test_tdi_tfsi_conflict_vetoes_strong(self):
        result = self._dd.score_pair(
            {
                "price": 16900, "mileage": 121000, "year": 2016,
                "title": "Audi A5 2.0 TDI",
            },
            {
                "price": 16740, "mileage": 121133, "year": "2016-03-01",
                "title": "Audi A5 Cabriolet 1.8TFSI",
            },
        )
        self.assertEqual(result["classification"], "LOW")
        self.assertIn("engine conflict: TDI vs TFSI", result["differences"])

    def test_model_designation_conflict_vetoes_strong(self):
        result = self._dd.score_pair(
            {
                "price": 32380, "mileage": 59200, "year": 2022,
                "title": "Audi A5 40 TDI",
            },
            {
                "price": 32680, "mileage": 58750, "year": 2022,
                "title": "Audi A5 Cabriolet 35 TDI",
            },
        )
        self.assertEqual(result["classification"], "LOW")
        self.assertIn(
            "model designation conflict: 40 vs 35", result["differences"]
        )

    def test_structured_signature_precedes_title_fallback(self):
        signature = self._dd._vehicle_signature({
            "title": "Audi A5 35 TFSI",
            "engine_family": "TDI",
            "model_designation": "40",
        })
        self.assertEqual(signature["engine_family"], "TDI")
        self.assertEqual(signature["model_designation"], "40")

    def test_model_variant_supplies_structured_signature(self):
        data = self._dd._listing_data(
            (1, 1, "source-1", 20000, 50000, "Dealer", None, None),
            {"title": "Audi A5", "model_variant": "40 TDI"},
        )
        signature = self._dd._vehicle_signature(data)
        self.assertEqual(signature["engine_family"], "TDI")
        self.assertEqual(signature["model_designation"], "40")

    def test_manual_automatic_is_strong_negative_evidence(self):
        base = {
            "price": 20000, "mileage": 50000, "year": 2020,
            "title": "Audi A5 40 TDI",
        }
        result = self._dd.score_pair(
            {**base, "transmission": "Schaltgetriebe"},
            {**base, "transmission": "Automatik"},
        )
        self.assertIn(
            "transmission conflict: manual vs auto", result["differences"]
        )
        self.assertLess(result["score"], 60)

    # ── Gearbox ───────────────────────────────────────────────────────────

    def _gearbox(self, s):
        return self._dd._norm_gearbox(s)

    def test_gearbox_de_en_equivalents(self):
        self.assertEqual(self._gearbox("Automatik"), self._gearbox("automatic"))
        self.assertEqual(self._gearbox("DSG"),       self._gearbox("auto"))
        self.assertEqual(self._gearbox("S Tronic"),  self._gearbox("Automatik"))
        self.assertEqual(self._gearbox("Schaltgetriebe"), self._gearbox("manual"))
        self.assertEqual(self._gearbox("manuell"),   self._gearbox("manual"))

    # ── Drivetrain ────────────────────────────────────────────────────────

    def _drive(self, s):
        return self._dd._norm_drive(s)

    def test_drive_equivalents(self):
        self.assertEqual(self._drive("Allrad"),  self._drive("AWD"))
        self.assertEqual(self._drive("quattro"), self._drive("4wd"))
        self.assertEqual(self._drive("4motion"), self._drive("awd"))
        self.assertEqual(self._drive("Frontantrieb"), self._drive("FWD"))
        self.assertEqual(self._drive("Hinterrad"),    self._drive("RWD"))

    # ── Evidence formatting ────────────────────────────────────────────────

    def test_price_evidence_uses_formatted_currency(self):
        """Price evidence must use € and dot-thousands separator."""
        a = {"price": 24990, "mileage": 39800, "seller": "Dealer"}
        b = {"price": 24990, "mileage": 39800, "seller": "Dealer"}
        result = self._dd.score_pair(a, b)
        self.assertTrue(
            any("€24.990" in r for r in result["reasons"]),
            f"Price evidence must show '€24.990': {result['reasons']}",
        )

    def test_mileage_evidence_uses_formatted_km(self):
        """Mileage evidence must use dot-thousands separator and ' km'."""
        a = {"price": 24990, "mileage": 39800, "seller": "Dealer"}
        b = {"price": 24990, "mileage": 39800, "seller": "Dealer"}
        result = self._dd.score_pair(a, b)
        self.assertTrue(
            any("39.800 km" in r for r in result["reasons"]),
            f"Mileage evidence must show '39.800 km': {result['reasons']}",
        )

    def test_exact_mileage_requires_equal_values(self):
        result = self._dd.score_pair(
            {"mileage": 195380},
            {"mileage": 195380},
        )
        self.assertEqual(result["reasons"], ["exact mileage: 195.380 km"])

    def test_close_mileage_wording_shows_both_values(self):
        result = self._dd.score_pair(
            {"mileage": 195380},
            {"mileage": 195823},
        )
        self.assertIn(
            "close mileage: 195.380 vs 195.823 km", result["reasons"]
        )
        self.assertFalse(any("exact mileage" in reason for reason in result["reasons"]))

    def test_different_mileage_wording(self):
        result = self._dd.score_pair(
            {"mileage": 100000},
            {"mileage": 120000},
        )
        self.assertTrue(
            any(diff.startswith("different mileage: 100.000 vs 120.000 km")
                for diff in result["differences"])
        )

    def test_close_price_is_not_described_as_exact(self):
        result = self._dd.score_pair(
            {"price": 24990},
            {"price": 25090},
        )
        self.assertIn("close price: €24.990 vs €25.090", result["reasons"])
        self.assertFalse(any("exact price" in reason for reason in result["reasons"]))

    def test_exact_price_requires_equal_values(self):
        result = self._dd.score_pair(
            {"price": 24990},
            {"price": 24990},
        )
        self.assertEqual(result["reasons"], ["exact price: €24.990"])

    def test_different_price_wording(self):
        result = self._dd.score_pair(
            {"price": 20000},
            {"price": 25000},
        )
        self.assertTrue(
            any(diff.startswith("different price: €20.000 vs €25.000")
                for diff in result["differences"])
        )

    def test_candidate_105_mileage_is_close_not_exact(self):
        result = self._dd.score_pair(
            {"price": 9999, "mileage": 195380},
            {"price": 9999, "mileage": 195823},
        )
        mileage_reasons = [
            reason for reason in result["reasons"] if "mileage" in reason
        ]
        self.assertEqual(
            mileage_reasons,
            ["close mileage: 195.380 vs 195.823 km"],
        )

    def test_structured_fuel_family_conflict_vetoes_strong(self):
        result = self._dd.score_pair(
            {
                "price": 24990, "mileage": 39800,
                "title": "Audi A5 Cabriolet", "fuel": "Diesel",
            },
            {
                "price": 24990, "mileage": 39800,
                "title": "Audi A5 Cabriolet", "fuel": "Benzin",
            },
        )
        self.assertEqual(result["classification"], "LOW")
        self.assertIn(
            "fuel family conflict: diesel vs petrol",
            result["differences"],
        )

    def test_registration_date_and_year_match(self):
        result = self._dd.score_pair(
            {"year": "2016"},
            {"first_registration": "2016-04-01"},
        )
        self.assertIn("same registration year: 2016", result["reasons"])

    def test_different_colour_is_negative_evidence(self):
        result = self._dd.score_pair(
            {"colour": "weiß"},
            {"colour": "black"},
        )
        self.assertEqual(result["score"], 0)
        self.assertIn("colour conflict: white vs black", result["differences"])

    def test_missing_colour_is_not_a_contradiction(self):
        result = self._dd.score_pair(
            {"colour": None},
            {"colour": "black"},
        )
        self.assertFalse(any("colour" in diff for diff in result["differences"]))

    def test_confirmed_same_possible_shape_becomes_strong(self):
        result = self._dd.score_pair(
            {
                "price": 9980, "mileage": 122621, "year": 2010,
                "title": "Audi A5 2.0 TFSI",
                "seller": (
                    "{'companyName': 'Autohaus Eggers', "
                    "'contactName': 'Yannick Hoppe'}"
                ),
            },
            {
                "price": 9980, "mileage": 122621,
                "first_registration": "2010-11-01",
                "title": "Audi A5 Cabriolet 2.0 TFSI",
                "seller": "Fahrzeugtechnik Yannick Hoppe",
            },
        )
        self.assertIn(result["classification"], ("STRONG", "VERY_STRONG"))
        self.assertIn("same seller contact: Yannick Hoppe", result["reasons"])

    def test_confirmed_different_possible_shape_is_low(self):
        result = self._dd.score_pair(
            {
                "price": 32380, "mileage": 59200, "year": 2022,
                "title": "Audi A5 40 TDI", "colour": "silber",
                "seller": "Audi Zentrum Trier",
            },
            {
                "price": 32680, "mileage": 58750, "year": 2022,
                "title": "Audi A5 35 TFSI", "colour": "rot",
                "seller": "Autohaus Rudolph",
            },
        )
        self.assertEqual(result["classification"], "LOW")

    def test_compatible_signature_with_unrelated_seller_stays_possible(self):
        result = self._dd.score_pair(
            {
                "price": 33980, "mileage": 39565, "year": 2022,
                "title": "Audi A5 35 TDI", "colour": "wit",
                "seller": "Fischer Automobile GmbH & Co. KG",
            },
            {
                "price": 34800, "mileage": 40306,
                "first_registration": "2022-05-01",
                "title": "Audi A5 Cabriolet S-Line 35 TDI S-Tronic",
                "colour": "weiß", "seller": "Nord Automobile",
            },
        )
        self.assertEqual(result["classification"], "POSSIBLE")
        self.assertIn(
            "seller conflict: Fischer Automobile GmbH & Co. KG vs Nord Automobile",
            result["differences"],
        )

    def test_scoring_is_source_neutral(self):
        a = {
            "source_id": 1, "price": 24990, "mileage": 39800,
            "title": "Audi A5 40 TDI", "seller": "Autohaus Beispiel",
        }
        b = {
            "source_id": 2, "price": 24990, "mileage": 39800,
            "title": "Audi A5 40 TDI", "seller": "Autohaus Beispiel",
        }
        forward = self._dd.score_pair(a, b)
        reverse_sources = self._dd.score_pair(
            {**a, "source_id": 999},
            {**b, "source_id": 1000},
        )
        self.assertEqual(forward, reverse_sources)

    def test_seller_evidence_shows_clean_name_not_dict(self):
        """Seller evidence must show extracted company name, not raw dict repr."""
        raw_seller = "{'dealer': {'companyName': 'Autogalerie Remscheid', 'id': '123'}}"
        a = {"price": 24990, "mileage": 39800, "seller": raw_seller}
        b = {"price": 24990, "mileage": 39800, "seller": "Autogalerie Remscheid"}
        result = self._dd.score_pair(a, b)
        seller_reasons = [r for r in result["reasons"] if "seller" in r.lower()]
        self.assertTrue(seller_reasons, "Must have a seller reason")
        self.assertNotIn("companyName", seller_reasons[0],
                         "Seller evidence must not contain raw dict key 'companyName'")
        self.assertIn("Autogalerie Remscheid", seller_reasons[0],
                      "Seller evidence must show clean company name")

    def test_colour_normalised_in_evidence(self):
        """Colour evidence must show the normalised canonical colour name."""
        a = {"price": 24990, "mileage": 39800, "colour": "zilver"}
        b = {"price": 24990, "mileage": 39800, "colour": "silber"}
        result = self._dd.score_pair(a, b)
        colour_reasons = [r for r in result["reasons"] if "colour" in r.lower()]
        self.assertTrue(colour_reasons, "Must have a colour reason")
        self.assertIn("silver", colour_reasons[0],
                      "Colour evidence must show normalised name 'silver'")

    def test_l60_l409_rescore(self):
        """L60/L409 pair must score correctly with clean seller evidence."""
        a = {
            "price": 24990, "mileage": 39800,
            "seller": "{'dealer': {'companyName': 'Autogalerie Remscheid'}}",
            "year": "2016", "title": "Audi A5 2.0 TFSI", "colour": "zilver",
        }
        b = {
            "price": 24990, "mileage": 39800,
            "seller": "Autogalerie Remscheid",
            "year": "2016", "title": "Audi A5 2.0 TFSI", "colour": "silber",
        }
        result = self._dd.score_pair(a, b)
        # Must match on seller
        self.assertTrue(
            any("same seller" in r and "Autogalerie Remscheid" in r for r in result["reasons"]),
            f"Must show clean seller match: {result['reasons']}",
        )
        # Must match on colour (zilver==silber==silver)
        self.assertTrue(
            any("same colour: silver" in r for r in result["reasons"]),
            f"Must show colour match: {result['reasons']}",
        )
        # Score must be STRONG or above
        self.assertGreaterEqual(result["score"], 60,
                                f"L60/L409 pair must score STRONG or above (got {result['score']})")
        # No differences
        self.assertEqual(result["differences"], [],
                         f"L60/L409 must have no differences: {result['differences']}")
