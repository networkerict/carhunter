"""
AutoHunter v2.6-dev
Deal analyzer
"""

import database
import deal_score
import debug


def update_deal_scores():

    cars = database.get_all_cars()

    updated = 0


    for car in cars:

        score = deal_score.calculate_deal_score(car)


        database.update_car_deal_score(
            car.id,
            score
        )

        updated += 1


    debug.info(
        f"Deal scores updated: {updated}"
    )


    return updated
