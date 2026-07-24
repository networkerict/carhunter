import os
import shutil
import tempfile
import unittest

import config
import database
import scraper
import telegram
from models import Car


class SoldDetectionTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="carhunter-test-", dir="/tmp")
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.original_database = config.DATABASE
        config.DATABASE = self.db_path
        database.get_connection().close()

    def tearDown(self):
        config.DATABASE = self.original_database
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_missing_cars_are_marked_sold_and_excluded_from_active_views(self):
        car_a = {
            "fingerprint": "a-fingerprint",
            "title": "Audi A5",
            "price": 25000,
            "km": 50000,
            "year": "2020",
            "url": "https://example.com/a",
            "color": "blauw",
            "color_detail": "Navarra Blau",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 184,
            "drive": "",
        }

        car_b = {
            "fingerprint": "b-fingerprint",
            "title": "Audi A5 Cabrio",
            "price": 30000,
            "km": 60000,
            "year": "2021",
            "url": "https://example.com/b",
            "color": "zwart",
            "color_detail": "Schwarz",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 204,
            "drive": "",
        }

        database.save_car(car_a)
        database.save_car(car_b)

        database.mark_missing_cars_sold([car_a["fingerprint"]])

        active_cars = database.search_cars()
        self.assertEqual([car.fingerprint for car in active_cars], ["a-fingerprint"])

        sold_car = next(car for car in database.get_all_cars() if car.fingerprint == "b-fingerprint")
        self.assertEqual(sold_car.sold, 1)
        self.assertTrue(sold_car.sold_at)

        database.save_car(car_b)
        active_cars = database.search_cars()
        self.assertEqual([car.fingerprint for car in active_cars], ["a-fingerprint", "b-fingerprint"])

        reappeared = next(car for car in database.get_all_cars() if car.fingerprint == "b-fingerprint")
        self.assertEqual(reappeared.sold, 0)

    def test_save_car_updates_existing_autoscout_id_without_duplicate(self):
        first = {
            "id": 123,
            "fingerprint": "fingerprint-one",
            "title": "Audi A5",
            "price": 25000,
            "km": 50000,
            "year": "2020",
            "url": "https://example.com/one",
            "color": "blauw",
            "color_detail": "Navarra Blau",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 184,
            "drive": "",
        }
        second = {
            "id": 123,
            "fingerprint": "fingerprint-two",
            "title": "Audi A5 Cabrio",
            "price": 30000,
            "km": 60000,
            "year": "2021",
            "url": "https://example.com/two",
            "color": "zwart",
            "color_detail": "Schwarz",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 204,
            "drive": "",
        }

        database.save_car(first)
        database.save_car(second)

        cars = database.get_all_cars()
        self.assertEqual(len(cars), 1)
        self.assertEqual(cars[0].fingerprint, "fingerprint-two")
        self.assertEqual(cars[0].title, "Audi A5 Cabrio")

    def test_car_model_maps_existing_database_layout_correctly(self):
        row = [
            1, 123, "fingerprint", "Audi A5", 25000, 50000, "2020",
            0, 0, 0, "https://example.com/a", "2024-01-01", "2024-01-02",
            0, "", "new", 20000, 0, 0, "", 0, "", "", 0,
            "blauw", "Navarra Blau", "leder", "schwarz", "S tronic", "Cabrio", 184,
            "quattro", "", 42, 1, 1, "2024-03-01", "silver", 0, "2024-03-02"
        ]

        car = Car(tuple(row))

        self.assertEqual(car.color, "blauw")
        self.assertEqual(car.color_detail, "Navarra Blau")
        self.assertEqual(car.upholstery, "leder")
        self.assertEqual(car.interior_color, "schwarz")
        self.assertEqual(car.personal_score, 42)
        self.assertEqual(car.watchlist_match, 1)
        self.assertEqual(car.sold, 0)
        self.assertEqual(car.sold_at, "2024-03-02")
        self.assertEqual(car.roof_color, "silver")

    def test_ranking_excludes_sold_cars(self):
        active_car = {
            "fingerprint": "active-fingerprint",
            "title": "Audi A5",
            "price": 25000,
            "km": 50000,
            "year": "2020",
            "url": "https://example.com/active",
            "color": "blauw",
            "color_detail": "Navarra Blau",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 184,
            "drive": "",
        }
        sold_car = {
            "fingerprint": "sold-fingerprint",
            "title": "Audi A5 Cabrio",
            "price": 30000,
            "km": 60000,
            "year": "2021",
            "url": "https://example.com/sold",
            "color": "zwart",
            "color_detail": "Schwarz",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 204,
            "drive": "",
        }

        database.save_car(active_car)
        database.save_car(sold_car)
        database.mark_missing_cars_sold([active_car["fingerprint"]])

        ranking = database.get_ranking(10)
        self.assertEqual([car.fingerprint for car in ranking], ["active-fingerprint"])

    def test_inventory_counts_include_active_new_and_sold(self):
        active_car = {
            "fingerprint": "active-fingerprint",
            "title": "Audi A5",
            "price": 25000,
            "km": 50000,
            "year": "2020",
            "url": "https://example.com/active",
            "color": "blauw",
            "color_detail": "Navarra Blau",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 184,
            "drive": "",
        }
        sold_car = {
            "fingerprint": "sold-fingerprint",
            "title": "Audi A5 Cabrio",
            "price": 30000,
            "km": 60000,
            "year": "2021",
            "url": "https://example.com/sold",
            "color": "zwart",
            "color_detail": "Schwarz",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 204,
            "drive": "",
        }

        database.save_car(active_car)
        database.save_car(sold_car)
        database.mark_missing_cars_sold([active_car["fingerprint"]])

        counts = database.get_inventory_counts()
        self.assertEqual(counts["active"], 1)
        self.assertEqual(counts["new"], 1)
        self.assertEqual(counts["sold"], 1)

    def test_mark_missing_cars_sold_returns_number_marked_sold(self):
        active_car = {
            "fingerprint": "active-fingerprint",
            "title": "Audi A5",
            "price": 25000,
            "km": 50000,
            "year": "2020",
            "url": "https://example.com/active",
            "color": "blauw",
            "color_detail": "Navarra Blau",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 184,
            "drive": "",
        }
        sold_car = {
            "fingerprint": "sold-fingerprint",
            "title": "Audi A5 Cabrio",
            "price": 30000,
            "km": 60000,
            "year": "2021",
            "url": "https://example.com/sold",
            "color": "zwart",
            "color_detail": "Schwarz",
            "upholstery": "",
            "interior_color": "",
            "gearbox": "",
            "body_type": "",
            "hp": 204,
            "drive": "",
        }

        database.save_car(active_car)
        database.save_car(sold_car)

        marked = database.mark_missing_cars_sold([active_car["fingerprint"]])

        self.assertEqual(marked, 1)

    def test_pipeline_summary_message_contains_run_and_database_metrics(self):
        message = telegram.build_pipeline_summary_message(
            run_stats={
                "status": "SUCCESS",
                "duration_seconds": 42,
                "new_cars": 3,
                "not_available_anymore": 2,
                "price_drops": 1,
                "high_score_cars": 4,
                "descriptions_updated": 5,
                "options_updated": 6,
                "alerts_sent": 7,
            },
            db_stats={
                "active_cars": 10,
                "not_available_anymore_total": 12,
            }
        )

        self.assertIn("SUCCESS", message)
        self.assertIn("Not available anymore: 2", message)
        self.assertIn("Active cars: 10", message)

    def test_save_car_preserves_specifications_from_vehicle_payload(self):
        listing_car = {
            "id": 999,
            "fingerprint": "spec-fingerprint",
            "title": "Audi A5",
            "price": {"priceRaw": 25000},
            "vehicle": {
                "make": "Audi",
                "model": "A5",
                "motorTypeName": "40 TFSI",
                "mileageInKm": "39251",
                "bodyType": "Cabrio",
                "rawPowerInHp": 204,
                "driveTrain": "Front",
                "transmissionType": "Automatik",
                "upholstery": "Teilleder",
                "upholsteryColor": "Schwarz",
            },
            "tracking": {"firstRegistration": "05/2023"},
            "url": "/angebote/test"
        }

        database.save_car(scraper.normalize_car(listing_car))

        stored = database.get_all_cars()[0]
        self.assertEqual(stored.body_type, "Cabrio")
        self.assertEqual(stored.hp, 204)
        self.assertEqual(stored.drive, "Front")
        self.assertEqual(stored.gearbox, "Automatik")
        self.assertEqual(stored.upholstery, "Teilleder")
        self.assertEqual(stored.interior_color, "Schwarz")


if __name__ == "__main__":
    unittest.main()
