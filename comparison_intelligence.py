#!/usr/bin/env python3

"""
AutoHunter v3.0-dev
Comparison intelligence engine
"""



def get_option_list(car):

    if not car.options_found:
        return []

    return [
        option.strip()
        for option in car.options_found.split(",")
        if option.strip()
    ]



def get_unique_options(winner, cars):

    import option_intelligence

    return option_intelligence.get_unique_advantages(
        winner,
        cars
    )


def analyze_comparison(cars):

    cars = [
        car
        for car in cars
        if car is not None
    ]


    if len(cars) < 2:
        return {
            "winner": None,
            "reasons": [],
            "warnings": [],
            "value": []
        }


    ranked = sorted(
        cars,
        key=lambda c: c.final_score,
        reverse=True
    )


    winner = ranked[0]

    reasons = []
    warnings = []
    value = []
    option_advantages = []


    if len(ranked) > 1:

        score_difference = (
            winner.final_score
            -
            ranked[1].final_score
        )

        if score_difference > 0:

            reasons.append(
                f"Hogere totaalscore (+{score_difference})"
            )


    option_difference = (
        winner.options_score
        -
        max(
            car.options_score
            for car in cars
            if car != winner
        )
    )


    if option_difference > 0:

        reasons.append(
            f"Meer opties (+{option_difference} punten)"
        )


    import option_intelligence


    option_advantages = (
        option_intelligence.sort_options_by_importance(
            option_intelligence.filter_premium_options(
                get_unique_options(
                    winner,
                    cars
                )
            )
        )[:5]
    )


    if winner.drive:

        reasons.append(
            f"Aandrijving: {winner.drive}"
        )


    if winner.hp:

        reasons.append(
            f"Vermogen: {winner.hp} pk"
        )


    priced_cars = [
        car for car in cars
        if getattr(car, "price", None) is not None
        and getattr(car, "price", None) != ""
    ]

    if priced_cars:
        cheapest = min(
            priced_cars,
            key=lambda c: c.price
        )

        if cheapest != winner:
            difference = (
                winner.price
                -
                cheapest.price
            )

            warnings.append(
                f"€{difference} duurder dan goedkoopste alternatief"
            )

    for car in priced_cars:
        ratio = round(
            car.final_score / (car.price / 1000),
            2
        )

        value.append(
            {
                "title": car.title,
                "ratio": ratio
            }
        )


    value = sorted(
        value,
        key=lambda x: x["ratio"],
        reverse=True
    )


    return {
        "winner": winner,
        "reasons": reasons,
        "warnings": warnings,
        "value": value,
        "option_advantages": option_advantages
    }
