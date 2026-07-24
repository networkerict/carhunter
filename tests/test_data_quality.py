import os
import shutil
import tempfile
import unittest
from unittest import mock

import config
import comparison_intelligence
import database
import data_quality
import scraper
import webapp


class DataQualityTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="carhunter-data-quality-", dir="/tmp")
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.original_database = config.DATABASE
        config.DATABASE = self.db_path
        database.get_connection().close()

    def tearDown(self):
        config.DATABASE = self.original_database
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_car(self, fingerprint, **overrides):
        payload = {
            "fingerprint": fingerprint,
            "title": "Audi A5",
            "price": 25000,
            "km": 50000,
            "year": "2020",
            "url": f"https://example.com/{fingerprint}",
            "color": "",
            "color_detail": "",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 0,
            "drive": "",
            "description": "",
            "options_found": "",
        }
        payload.update(overrides)
        database.save_car(payload)
        return database.get_all_cars()[-1]

    def test_backfill_updates_only_missing_fields_and_dry_run(self):
        car = self._create_car("a", body_type="", upholstery="", description="")
        existing_car = self._create_car("b", body_type="Cabrio", upholstery="Leder", description="keep")

        detail_payload = {
            "body_type": "Coupé",
            "hp": 204,
            "drive": "Quattro",
            "upholstery": "Vollleder",
            "interior_color": "Schwarz",
            "gearbox": "Automatik",
            "color": "Schwarz",
            "color_detail": "Mythosschwarz",
            "description": "fresh description",
            "options_found": "ABC",
        }

        with mock.patch.object(scraper, "fetch_car_details", return_value=detail_payload), \
             mock.patch.object(scraper, "fetch_description", return_value="fresh description"):
            engine = data_quality.BackfillEngine()
            result = engine.run_backfill(limit=1, batch_size=1, dry_run=False)

        self.assertEqual(result["updated"], 1)
        updated = database.get_car(car.id)
        self.assertEqual(updated.body_type, "Coupé")
        self.assertEqual(updated.upholstery, "Vollleder")
        self.assertEqual(updated.description, "fresh description")

        untouched = database.get_car(existing_car.id)
        self.assertEqual(untouched.body_type, "Cabrio")
        self.assertEqual(untouched.description, "keep")

    def test_dry_run_does_not_persist_changes(self):
        car = self._create_car("dry")
        detail_payload = {
            "body_type": "Coupé",
            "hp": 204,
            "drive": "Quattro",
            "upholstery": "Vollleder",
            "interior_color": "Schwarz",
            "gearbox": "Automatik",
            "color": "Schwarz",
            "color_detail": "Mythosschwarz",
            "description": "fresh description",
            "options_found": "ABC",
        }

        with mock.patch.object(scraper, "fetch_car_details", return_value=detail_payload), \
             mock.patch.object(scraper, "fetch_description", return_value="fresh description"):
            engine = data_quality.BackfillEngine()
            result = engine.run_backfill(limit=1, batch_size=1, dry_run=True)

        self.assertEqual(result["updated"], 0)
        reloaded = database.get_car(car.id)
        self.assertEqual(reloaded.body_type, "")
        self.assertEqual(reloaded.description, "")

    def test_backfill_resume_after_interruption(self):
        self._create_car("resume-a")
        self._create_car("resume-b")

        detail_payload = {
            "body_type": "Coupé",
            "hp": 204,
            "drive": "Quattro",
            "upholstery": "Vollleder",
            "interior_color": "Schwarz",
            "gearbox": "Automatik",
            "color": "Schwarz",
            "color_detail": "Mythosschwarz",
            "description": "fresh description",
            "options_found": "ABC",
        }

        with mock.patch.object(scraper, "fetch_car_details", return_value=detail_payload), \
             mock.patch.object(scraper, "fetch_description", return_value="fresh description"):
            engine = data_quality.BackfillEngine()
            first = engine.run_backfill(limit=1, batch_size=1, dry_run=False, resume=False)
            second = engine.run_backfill(limit=2, batch_size=1, dry_run=False, resume=True)

        self.assertEqual(first["processed"], 1)
        self.assertEqual(second["processed"], 1)
        self.assertEqual(second["updated"], 1)

    def test_dashboard_statistics_and_integrity_checks(self):
        self._create_car("dq-a", body_type="Cabrio", gearbox="Automatik", drive="Quattro", hp=204, color="Schwarz", color_detail="Mythosschwarz", upholstery="Vollleder", interior_color="Schwarz", description="ok")
        self._create_car("dq-b", body_type="", gearbox="", drive="", hp=0, color="", color_detail="", upholstery="", interior_color="", description="")

        stats = data_quality.get_dashboard_summary()
        self.assertGreaterEqual(stats["total_vehicles"], 2)
        self.assertGreaterEqual(stats["complete_vehicles"], 1)
        self.assertGreaterEqual(stats["incomplete_vehicles"], 1)
        self.assertGreaterEqual(stats["missing_specifications"], 1)

        integrity = data_quality.run_integrity_checks()
        self.assertEqual(integrity["summary"]["unexpected_missing"], 0)
        self.assertGreaterEqual(integrity["summary"]["expected_missing"], 1)

    def test_save_car_preserves_existing_price_when_new_payload_has_no_price(self):
        self._create_car("price-preserve", price=38490)

        database.save_car({
            "fingerprint": "price-preserve",
            "title": "Audi A5",
            "price": None,
            "km": 39251,
            "year": "2023",
            "url": "https://example.com/price-preserve",
            "color": "",
            "color_detail": "",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 0,
            "drive": "",
            "description": "",
            "options_found": "",
        })

        reloaded = database.get_car(1)
        self.assertEqual(reloaded.price, 38490)
        self.assertEqual(reloaded.last_price, 38490)

    def test_analyze_comparison_ignores_cars_without_valid_price(self):
        class DummyCar:
            def __init__(self, price, final_score=80, options_score=0, drive="", hp=0, title=""):
                self.price = price
                self.final_score = final_score
                self.options_score = options_score
                self.drive = drive
                self.hp = hp
                self.title = title
                self.options_found = ""

        cars = [
            DummyCar(25000, final_score=90, title="Cheap"),
            DummyCar(None, final_score=85, title="Missing price"),
        ]

        result = comparison_intelligence.analyze_comparison(cars)

        self.assertEqual(result["winner"].title, "Cheap")
        self.assertEqual(result["value"][0]["title"], "Cheap")

    def test_car_detail_hides_specifications_section_when_no_data_exists(self):
        database.save_car({
            "fingerprint": "specs-empty",
            "title": "Audi A5",
            "price": 25000,
            "km": 50000,
            "year": "2020",
            "url": "https://example.com/specs-empty",
            "color": "",
            "color_detail": "",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 0,
            "drive": "",
            "description": "",
            "options_found": "",
        })

        client = webapp.app.test_client()
        response = client.get("/car/1")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("Specificaties", html)
        self.assertNotIn("No specifications available", html)

    def test_car_detail_shows_specifications_section_when_data_exists(self):
        database.save_car({
            "fingerprint": "specs-present",
            "title": "Audi A5",
            "price": 25000,
            "km": 50000,
            "year": "2020",
            "url": "https://example.com/specs-present",
            "color": "",
            "color_detail": "",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "Automatik",
            "body_type": "Cabrio",
            "hp": 204,
            "drive": "Front",
            "description": "",
            "options_found": "",
        })

        client = webapp.app.test_client()
        response = client.get("/car/1")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Specificaties", html)
        self.assertIn("Cabrio", html)
        self.assertIn("204 pk", html)
