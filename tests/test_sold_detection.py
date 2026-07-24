import os
import shutil
import tempfile
import unittest

import config
import database


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


if __name__ == "__main__":
    unittest.main()
