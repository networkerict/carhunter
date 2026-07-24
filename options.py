#!/usr/bin/env python3

"""
AutoHunter v2.9-dev
Option analysis engine
"""

import database
import debug

OPTION_MAX_REALISTIC = 125

OPTION_POINTS = {

    "S line": {
        "points": 15,
        "aliases": [
            "s line",
            "s-line"
        ]
    },

    "quattro": {
        "points": 15,
        "aliases": [
            "quattro",
            "allrad"
        ]
    },

    "Matrix LED": {
        "points": 10,
        "aliases": [
            "matrix led",
            "matrix-led",
            "matrixlicht"
        ]
    },

    "Laser verlichting": {
        "points": 8,
        "aliases": [
            "laserlicht",
            "laser"
        ]
    },

    "Head-up display": {
        "points": 10,
        "aliases": [
            "head-up",
            "head up display",
            "hud"
        ]
    },

    "Adaptive cruise control": {
        "points": 10,
        "aliases": [
            "adaptive cruise",
            "abstandstempomat",
            "acc"
        ]
    },

    "360 camera": {
        "points": 8,
        "aliases": [
            "360 kamera",
            "360 camera"
        ]
    },

    "Achteruitrijcamera": {
        "points": 5,
        "aliases": [
            "rückfahrkamera",
            "achteruitrijcamera",
            "kamera"
        ]
    },

    "Leder interieur": {
        "points": 8,
        "aliases": [
            "lederausstattung",
            "leder interieur",
            "leder"
        ]
    },

    "Sportstoelen": {
        "points": 7,
        "aliases": [
            "sportsitze",
            "sportstoelen"
        ]
    },

    "Memory stoelen": {
        "points": 5,
        "aliases": [
            "memory",
            "memorysitze"
        ]
    },

    "Elektrische stoelen": {
        "points": 5,
        "aliases": [
            "elektrische sitze",
            "elektr. sitze"
        ]
    },

    "Stoelverwarming": {
        "points": 5,
        "aliases": [
            "sitzheizung",
            "stoelverwarming"
        ]
    },

    "Nekverwarming": {
        "points": 10,
        "aliases": [
            "airscarf",
            "neck heater",
            "nekverwarming"
        ]
    },

    "Virtual cockpit": {
        "points": 5,
        "aliases": [
            "virtual cockpit",
            "volldigitales kombiinstrument"
        ]
    },

    "MMI Navigation Plus": {
        "points": 5,
        "aliases": [
            "mmi navigation plus",
            "mmi plus",
            "navigationssystem",
            "navigation"
        ]
    },

    "Bang & Olufsen": {
        "points": 8,
        "aliases": [
            "bang & olufsen",
            "bang olufsen",
            "b&o",
            "advanced sound"
        ]
    },

    "Alcantara": {
        "points": 5,
        "aliases": [
            "alcantara",
            "alcantaraausstattung"
        ]
    },

    "Keyless": {
        "points": 5,
        "aliases": [
            "keyless",
            "schlüssellose zentralverriegelung",
            "komfortzugang"
        ]
    },

    "Parkeersensoren": {
        "points": 4,
        "aliases": [
            "einparkhilfe",
            "parksensoren",
            "parkhilfe"
        ]
    },

    "Klimaautomatik": {
        "points": 3,
        "aliases": [
            "klimaautomatik",
            "automatische klimaanlage"
        ]
    },

    "Xenon verlichting": {
        "points": 4,
        "aliases": [
            "xenon",
            "bi-xenon",
            "bi-xenon scheinwerfer"
        ]
    },

    "Windschot": {
        "points": 8,
        "aliases": [
            "windschott",
            "windschot",
            "wind deflector"
        ]
    },

}


def analyze_options(car, explain=False):

    found = []
    score = 0
    breakdown = []

    texts = []


    if isinstance(car, dict):

        description = car.get(
            "description",
            ""
        )

        car_options = car.get(
            "options",
            []
        )

        title = car.get(
            "title",
            ""
        )

    else:

        description = getattr(
            car,
            "description",
            ""
        )

        car_options = getattr(
            car,
            "options",
            []
        )

        title = getattr(
            car,
            "title",
            ""
        )


    if description:
        texts.append(description.lower())

    if title:
        texts.append(title.lower())

    if car_options:
        texts.extend(
            [
                option.lower()
                for option in car_options
            ]
        )

    if isinstance(car, dict):

        upholstery = car.get(
            "upholstery",
            ""
        )

        if upholstery:
            texts.append(
                upholstery.lower()
            )


    text = " ".join(texts)


    for option, data in OPTION_POINTS.items():

        for alias in data["aliases"]:

            if alias.lower() in text:

                found.append(option)

                score += data["points"]

                breakdown.append(
                    {
                        "option": option,
                        "points": data["points"]
                    }
                )

                break


    if explain:
        return found, score, breakdown


    return found, score


def update_all_options():

    debug.info(
        "Starting option update"
    )

    cars = database.get_all_cars()

    debug.info(
        f"Cars found: {len(cars)}"
    )

    updated = 0


    for car in cars:

        if car.options_checked:
            continue

        result = update_car_options(car)

        if result:
            updated += 1


    debug.info(
        f"Options updated: {updated}"
    )

    return updated


def update_car_options(car):

    debug.info(
        f"Checking options: {car.title}"
    )


    found, score = analyze_options(
        car
    )


    debug.info(
        f"Found: {found}"
    )


    debug.info(
        f"Score: {score}"
    )


    database.update_car_options(
        car.id,
        ", ".join(found),
        score
    )


    return True
