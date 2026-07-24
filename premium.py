#!/usr/bin/env python3

"""
AutoHunter v2.5
Premium vehicle scoring
"""

import re


PREMIUM_POINTS = {

    "45 TFSI": {
        "points": 10,
        "aliases": [
            "45 tfsi",
            "195 kw"
        ]
    },

    "Bang & Olufsen": {
        "points": 5,
        "aliases": [
            "bang & olufsen",
            "b&o",
            "premium soundsystem"
        ]
    },

    "Massage seats": {
        "points": 5,
        "aliases": [
            "massage",
            "massagefunktion"
        ]
    },

    "Seat ventilation": {
        "points": 5,
        "aliases": [
            "sitzbelüftung",
            "sitzbelueftung"
        ]
    },

    "Magnetic Ride": {
        "points": 4,
        "aliases": [
            "magnetic ride",
            "dämpferregelung"
        ]
    },

    "20 inch Audi Sport wheels": {
        "points": 3,
        "aliases": [
            "20",
            "9,0j"
        ]
    },

    "First owner": {
        "points": 3,
        "aliases": [
            "1. hand",
            "1 vorbesitzer",
            "1 vorhalter"
        ]
    },

    "Audi warranty": {
        "points": 3,
        "aliases": [
            "audi garantie",
            "anschlussgarantie"
        ]
    }
}


def analyze_premium(car, explain=False):

    text = (
        (car.title or "")
        + " "
        + (car.description or "")
    ).lower()

    score = 0
    breakdown = []


    for option, data in PREMIUM_POINTS.items():

        for alias in data["aliases"]:

            if alias.lower() in text:

                score += data["points"]

                breakdown.append(
                    {
                        "points": data["points"],
                        "reason": option
                    }
                )

                break


    if explain:
        return score, breakdown


    return score
