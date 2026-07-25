#!/usr/bin/env python3

"""
AutoHunter v2.9
Value intelligence engine
"""


def calculate_value_ratio(car):

    if not car.price:
        return 0


    return round(
        car.final_score / (car.price / 1000),
        2
    )



def analyze_value(cars):

    results = []


    for car in cars:

        results.append(
            {
                "car": car,
                "ratio": calculate_value_ratio(car)
            }
        )


    return sorted(
        results,
        key=lambda x: x["ratio"],
        reverse=True
    )




def compare_value_to_winner(value_car, winner):

    price_difference = (
        winner.price
        -
        value_car.price
    )


    score_difference = (
        winner.final_score
        -
        value_car.final_score
    )


    return {

        "saved_money": price_difference,

        "lost_score": score_difference,

        "message":
            f"€{price_difference} goedkoper "
            f"voor slechts {score_difference} punten minder score"

    }


def explain_value(cars):

    ranked = analyze_value(cars)

    if not ranked:
        return None


    return ranked[0]
