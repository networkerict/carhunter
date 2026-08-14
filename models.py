"""
AutoHunter v3.0-dev
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

        if len(row) > 39 and isinstance(row[24], str):
            color_index = 24
            color_detail_index = 25
            upholstery_index = 26
            interior_color_index = 27
            gearbox_index = 28
            body_type_index = 29
            hp_index = 30
            drive_index = 31
            options_checked_at_index = 32
            personal_score_index = 33
            watchlist_match_index = 34
            telegram_sent_index = 35
            telegram_sent_at_index = 36
            roof_color_index = 37
            sold_index = 38
            sold_at_index = 39
            last_modified_index = 40 if len(row) > 40 else None
        else:
            color_index = 26
            color_detail_index = 27
            upholstery_index = 28
            interior_color_index = 29
            gearbox_index = 30
            body_type_index = 31
            hp_index = 32
            drive_index = 33
            options_checked_at_index = 34
            personal_score_index = 35
            watchlist_match_index = 36
            telegram_sent_index = 37
            telegram_sent_at_index = 38
            roof_color_index = 39
            sold_index = 24
            sold_at_index = 25
            last_modified_index = 40 if len(row) > 40 else None

        self.sold = row[sold_index] if len(row) > sold_index else 0
        self.sold_at = row[sold_at_index] if len(row) > sold_at_index else None
        self.color = row[color_index] if len(row) > color_index else ""
        self.color_detail = row[color_detail_index] if len(row) > color_detail_index else ""

        self.upholstery = row[upholstery_index] if len(row) > upholstery_index else ""
        self.interior_color = row[interior_color_index] if len(row) > interior_color_index else ""
        self.roof_color = row[roof_color_index] if len(row) > roof_color_index else ""

        self.gearbox = row[gearbox_index] if len(row) > gearbox_index else ""
        self.body_type = row[body_type_index] if len(row) > body_type_index else ""

        self.hp = row[hp_index] if len(row) > hp_index else ""
        self.drive = row[drive_index] if len(row) > drive_index else ""
        self.options_checked_at = row[options_checked_at_index] if len(row) > options_checked_at_index else None
        self.last_modified = row[last_modified_index] if last_modified_index is not None and len(row) > last_modified_index else None

        self.personal_score = row[personal_score_index] if len(row) > personal_score_index else 0
        self.watchlist_match = row[watchlist_match_index] if len(row) > watchlist_match_index else 0

        self.telegram_sent = row[telegram_sent_index] if len(row) > telegram_sent_index else 0
        self.telegram_sent_at = row[telegram_sent_at_index] if len(row) > telegram_sent_at_index else None

        # Source identity — populated by database enrichment helpers, not by row columns.
        self.source_name = None
        self.source_label = "Listing"


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
