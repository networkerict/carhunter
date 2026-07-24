import os
import shutil
import tempfile
import unittest
from unittest import mock

import config
import database
import repair_engine
import scraper


class RepairEngineTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="carhunter-repair-", dir="/tmp")
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
            "color": "Schwarz",
            "color_detail": "Mythosschwarz",
            "upholstery": "Teilleder",
            "interior_color": "Schwarz",
            "gearbox": "Automatik",
            "body_type": "Cabrio",
            "hp": 204,
            "drive": "Front",
            "description": "complete",
            "options_found": "S line",
        }
        payload.update(overrides)
        database.save_car(payload)
        return database.get_all_cars()[-1]

    def test_safe_merge_preserves_existing_value_when_incoming_is_none(self):
        self.assertEqual(repair_engine._merge_value(38490, None, "price"), 38490)

    def test_safe_merge_preserves_existing_value_when_incoming_is_empty_string(self):
        self.assertEqual(repair_engine._merge_value("S tronic", "", "gearbox"), "S tronic")

    def test_safe_merge_replaces_existing_value_when_incoming_is_better(self):
        self.assertEqual(repair_engine._merge_value("Automatik", "S tronic", "gearbox"), "S tronic")

    def test_run_repair_updates_incomplete_cars(self):
        incomplete = self._create_car("incomplete", price=None, body_type="", gearbox="", description="")
        complete = self._create_car("complete", description="already complete", options_found="S line")

        detail_payload = {
            "price": 21990,
            "km": 39251,
            "year": "2023",
            "color": "Blau",
            "color_detail": "Navarra Blau",
            "upholstery": "Vollleder",
            "interior_color": "Schwarz",
            "gearbox": "S tronic",
            "body_type": "Cabrio",
            "hp": 204,
            "drive": "Quattro",
            "description": "Fresh description",
            "options_found": "S line, Matrix LED",
        }

        with mock.patch.object(scraper, "fetch_car_details", return_value=detail_payload), \
             mock.patch.object(scraper, "fetch_description", return_value="Fresh description"):
            report = repair_engine.run_repair(dry_run=False)

        self.assertEqual(report["cars_checked"], 2)
        self.assertEqual(report["cars_repaired"], 1)
        repaired = database.get_car(incomplete.id)
        self.assertEqual(repaired.price, 21990)
        self.assertEqual(repaired.gearbox, "S tronic")
        self.assertEqual(repaired.description, "Fresh description")
        self.assertEqual(repaired.options_found, "S line, Matrix LED")

        unchanged = database.get_car(complete.id)
        self.assertEqual(unchanged.description, "already complete")
        self.assertEqual(unchanged.options_found, "S line")

    def test_run_repair_dry_run_leaves_database_unchanged(self):
        incomplete = self._create_car("dry-run", price=None, description="")

        detail_payload = {
            "price": 21990,
            "description": "Fresh description",
        }

        with mock.patch.object(scraper, "fetch_car_details", return_value=detail_payload), \
             mock.patch.object(scraper, "fetch_description", return_value="Fresh description"):
            report = repair_engine.run_repair(dry_run=True)

        self.assertTrue(report["dry_run"])
        reloaded = database.get_car(incomplete.id)
        self.assertIsNone(reloaded.price)
        self.assertEqual(reloaded.description, "")

    def test_run_repair_persists_last_modified_and_continues_after_failure(self):
        first = self._create_car("write-1", price=None, body_type="")
        second = self._create_car("write-2", price=None, body_type="")

        detail_payload = {
            "price": 21990,
            "body_type": "Cabrio",
            "description": "Fresh description",
        }

        def fake_fetch_car_details(url):
            if "write-1" in url:
                return detail_payload
            if "write-2" in url:
                raise RuntimeError("boom")
            return None

        with mock.patch.object(scraper, "fetch_car_details", side_effect=fake_fetch_car_details), \
             mock.patch.object(scraper, "fetch_description", return_value="Fresh description"):
            report = repair_engine.run_repair(dry_run=False)

        self.assertEqual(report["cars_repaired"], 1)
        self.assertEqual(report["cars_unavailable"], 1)

        repaired = database.get_car(first.id)
        self.assertEqual(repaired.price, 21990)
        self.assertEqual(repaired.body_type, "Cabrio")
        self.assertTrue(repaired.last_modified)
