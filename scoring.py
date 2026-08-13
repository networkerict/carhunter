#!/usr/bin/env python3

"""
AutoHunter v2.4
Scoring engine
"""

import database
import debug
import premium
import options
import sqlite3
from database import get_connection
import matcher
import watchlist

def calculate_car_score(car, explain=False):

    title = str(getattr(car, "title", "") or "").lower()
    description = str(getattr(car, "description", "") or "").lower()

    supported_variants = ("45 tfsi", "40 tfsi", "40 tdi")
    text = title if any(variant in title for variant in supported_variants) else description


    score = 0
    breakdown = []


    def add(points, reason):
        nonlocal score
        score += points

        breakdown.append(
            {
                "points": points,
                "reason": reason
            }
        )


    if "45 tfsi" in text:
        add(30, "45 TFSI")

    elif "40 tfsi" in text:
        add(15, "40 TFSI")

    elif "40 tdi" in text:
        add(5, "40 TDI")


    year = str(getattr(car, "year", ""))

    if year:
        try:
            model_year = int(year[-4:])

            if model_year >= 2024:
                add(15, "Bouwjaar >= 2024")

            elif model_year >= 2023:
                add(10, "Bouwjaar >= 2023")

            elif model_year >= 2022:
                add(5, "Bouwjaar >= 2022")

        except:
            pass


    km = car.km

    if km is not None and km < 20000:
        add(10, "<20.000 km")

    elif km is not None and km < 40000:
        add(5, "<40.000 km")


    if explain:
        return score, breakdown


    return score



def calculate_value_score(car, explain=False):

    price = car.price or 0
    if price == 0:
        if explain:
            return 0, [
                {
                    "points": 0,
                    "reason": "Geen prijs beschikbaar"
                }
            ]

        return 0

    km = car.km


    score = 50
    breakdown = [
        {
            "points": 50,
            "reason": "Basis waarde score"
        }
    ]


    def add(points, reason):
        nonlocal score

        score += points

        breakdown.append(
            {
                "points": points,
                "reason": reason
            }
        )


    if price < 40000:
        add(20, "Prijs < €40.000")

    elif price < 45000:
        add(15, "Prijs < €45.000")

    elif price < 50000:
        add(5, "Prijs < €50.000")


    if km is not None and km < 30000:
        add(15, "<30.000 km")

    elif km is not None and km < 50000:
        add(10, "<50.000 km")


    if explain:
        return score, breakdown


    return score


#def recalculate_scores():
#
#    debug.info(
#        "Starting score recalculation"
#    )
#
#
#    conn = database.get_connection()
#
#    cars = database.get_all_cars()
#
#
#    debug.info(
#        f"Cars found: {len(cars)}"
#    )
#
#
#    conn = database.get_connection()
#
#    try:
#
#        for car in cars:
#
#            car_score, value_score, premium_score, final = calculate_final_score(car)
#
#            debug.info(
#                f"{car.title}: {final}"
#            )
#
#
#            database.update_car_scores(
#                car.id,
#                car_score,
#                value_score,
#                premium_score,
#                final,
#                conn=conn
#            )
#
#        conn.commit()
#
#    finally:
#
#        conn.close()

def recalculate_scores():

    debug.info(
        "Starting score recalculation"
    )

    conn = database.get_connection()

    try:

        conn.execute(
            "BEGIN TRANSACTION"
        )

        cars = database.get_all_cars(conn)

        debug.info(
            f"Cars found: {len(cars)}"
        )

        for car in cars:

            car_score, value_score, premium_score, final = calculate_final_score(car)

            debug.debug(
                f"{car.title}: {final}"
            )

            watchlist_match = matcher.matches_watchlist(car)

            personal_score = matcher.calculate_personal_score(car)

            database.update_car_scores(
                car.id,
                car_score,
                value_score,
                premium_score,
                final,
                personal_score,
                int(watchlist_match),
                conn
            )

        conn.commit()

        debug.info(
            "Score recalculation committed"
        )


    except Exception as e:

        conn.rollback()

        debug.error(
            f"Score recalculation failed: {e}"
        )

        raise


    finally:

        conn.close()


def recalculate_all_scores():
    import orchestration

    orchestration.run_pipeline(
        "rescore"
    )


def calculate_final_score(car):

    car_score = calculate_car_score(car)

    value_score = calculate_value_score(car)

    raw_options = car.options_score or 0

    premium_score = premium.analyze_premium(car)

    MAX_OPTION_SCORE = options.OPTION_MAX_REALISTIC

    options_normalized = raw_options / MAX_OPTION_SCORE


    final = int(
        (
            car_score * 0.35
        )
        +
        (
            value_score * 0.25
        )
        +
        (
            options_normalized * 25
        )
        +
        (
            premium_score
        )
    )


    return (
        car_score,
        value_score,
        premium_score,
        final
    )
