#!/usr/bin/env python3

"""
AutoHunter v2.5
Description updater
"""

import database
import debug
import scraper


def update_missing_descriptions():

    cars = database.get_all_cars()

    debug.info(
        f"Cars found: {len(cars)}"
    )

    existing = 0
    updated = 0
    missing = 0


    for car in cars:

        if car.description:

            existing += 1
            continue


        debug.info(
            f"Fetching description: {car.id}"
        )


        description = scraper.fetch_description(
            car.url
        )


        if description:

            database.update_car_description(
                car.id,
                description
            )

            updated += 1

            debug.info(
                f"Updated {car.id}: {len(description)} chars"
            )

        else:

            missing += 1

            debug.info(
                f"No description: {car.id}"
            )


    debug.info(
        f"Descriptions available: {existing}"
    )

    debug.info(
        f"Descriptions updated: {updated}"
    )

    debug.info(
        f"Descriptions missing: {missing}"
    )

    return updated
