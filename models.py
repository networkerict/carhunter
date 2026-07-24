"""
AutoHunter v2.9-dev
Data models
"""


class Car:

    def __init__(self, row):

        self.id = row[0]
        self.autoscout_id = row[1]
        self.fingerprint = row[2]

        self.title = row[3]

        self.price = row[4]
        self.km = row[5]
        self.year = row[6]

        self.car_score = row[7]
        self.value_score = row[8]
        self.final_score = row[9]

        self.url = row[10]

        self.first_seen = row[11]
        self.last_seen = row[12]

        self.options_score = row[13]
        self.premium_score = row[23] if len(row) > 23 else 0
        self.options_found = row[14]

        self.status = row[15]

        self.last_price = row[16]
        self.price_drop = row[17]
        self.alert = row[18]

        self.recommendation = row[19]

        self.deal_score = row[20]

        self.options_checked = row[21]

        self.description = row[22]
        self.sold = row[24] if len(row) > 24 else 0
        self.sold_at = row[25] if len(row) > 25 else None
        self.color = row[26] if len(row) > 26 else ""
        self.color_detail = row[27] if len(row) > 27 else ""

        self.upholstery = row[28] if len(row) > 28 else ""
        self.interior_color = row[29] if len(row) > 29 else ""
        self.roof_color = row[39] if len(row) > 39 else ""

        self.gearbox = row[30] if len(row) > 30 else ""
        self.body_type = row[31] if len(row) > 31 else ""

        self.hp = row[32] if len(row) > 32 else ""
        self.drive = row[33] if len(row) > 33 else ""
        self.options_checked_at = row[34] if len(row) > 34 else None

        self.personal_score = row[35] if len(row) > 35 else 0
        self.watchlist_match = row[36] if len(row) > 36 else 0

        self.telegram_sent = row[37] if len(row) > 37 else 0
        self.telegram_sent_at = row[38] if len(row) > 38 else None


    def summary(self):

        return {
            "id": self.id,
            "title": self.title,
            "price": self.price,
            "km": self.km,
            "year": self.year,
            "score": self.final_score,
            "options": self.options_found
        }
