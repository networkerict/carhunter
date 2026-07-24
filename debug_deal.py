"""
AutoHunter v2.6-dev
Deal score explanation
"""


def explain_deal(car):

    reasons = []

    score = 0


    # Hoge AutoHunter score

    if car.final_score >= 85:

        points = 40
        score += points

        reasons.append(
            f"⭐ Zeer hoge AutoHunter score: +{points}"
        )


    elif car.final_score >= 80:

        points = 25
        score += points

        reasons.append(
            f"⭐ Hoge AutoHunter score: +{points}"
        )


    # Prijsdaling

    if car.price_drop:

        if car.price_drop >= 2000:

            points = 20
            score += points

            reasons.append(
                f"🔻 Grote prijsdaling (€{car.price_drop}): +{points}"
            )


        elif car.price_drop >= 1000:

            points = 10
            score += points

            reasons.append(
                f"🔻 Prijsdaling (€{car.price_drop}): +{points}"
            )


    # Opties

    if car.options_score >= 80:

        points = 10
        score += points

        reasons.append(
            f"🎯 Veel opties ({car.options_score}): +{points}"
        )


    # Nieuwe auto

    if car.status == "new":

        points = 5
        score += points

        reasons.append(
            f"🆕 Nieuwe advertentie: +{points}"
        )


    return score, reasons
