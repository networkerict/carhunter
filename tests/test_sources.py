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

