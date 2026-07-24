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
        self.premium_score = row[23]
        self.options_found = row[14]

        self.status = row[15]

        self.last_price = row[16]
        self.price_drop = row[17]
        self.alert = row[18]

        self.recommendation = row[19]

        self.deal_score = row[20]

        self.options_checked = row[21]

        self.description = row[22]
        self.color = row[24]
        self.color_detail = row[25]

        self.upholstery = row[26]
        self.interior_color = row[27]
        self.roof_color = row[37]

        self.gearbox = row[28]
        self.body_type = row[29]

        self.hp = row[30]
        self.drive = row[31]
        self.options_checked_at = row[32]

        self.personal_score = row[33]
        self.watchlist_match = row[34]

        self.telegram_sent = row[35]
        self.telegram_sent_at = row[36]


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
