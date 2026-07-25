"""
AutoHunter v2.9
Vehicle recommendation engine
"""


def explain_car(car):

    reasons = []


    if car.watchlist_match == 1:

        reasons.append(
            "Past binnen persoonlijke watchlist"
        )


    if car.personal_score >= 80:

        reasons.append(
            "Sterke persoonlijke match"
        )


    if car.color:

        if car.watchlist_match == 1:

            reasons.append(
                f"Kleurmatch: {car.color}"
            )


    if car.deal_score >= 40:

        reasons.append(
            "Interessante deal"
        )


    if car.options_score >= 50:

        reasons.append(
            "Veel waardevolle opties"
        )


    if car.premium_score >= 10:

        reasons.append(
            "Premium uitvoering"
        )


    if car.price_drop and car.price_drop > 0:

        reasons.append(
            f"Prijs verlaagd met €{car.price_drop}"
        )


    if car.year:

        try:

            year = int(str(car.year)[-4:])

            if year >= 2022:

                reasons.append(
                    "Recent bouwjaar"
                )

        except:

            pass


    if car.options_found:

        reasons.append(
            "Uitgerust met gewenste opties"
        )


    return reasons
