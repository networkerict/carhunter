import unittest

import scraper
import webapp


class NumericFormattingTests(unittest.TestCase):

    def test_normalize_car_reads_price_from_value_raw_fallback(self):
        payload = {
            "vehicle": {
                "make": "Audi",
                "model": "A5",
                "motorTypeName": "40 TDI",
            },
            "price": {"value": {"raw": 24500}},
            "tracking": {"firstRegistration": "2023-05-01"},
            "url": "/angebote/test",
        }

        normalized = scraper.normalize_car(payload)

        self.assertEqual(normalized["price"], 24500)

    def test_currency_filter_renders_dash_for_missing_values(self):
        self.assertEqual(webapp.format_currency(None), "—")
        self.assertEqual(webapp.format_currency(""), "—")
