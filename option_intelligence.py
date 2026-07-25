#!/usr/bin/env python3

"""
AutoHunter v2.9
Option intelligence normalization
"""


IGNORE_OPTIONS = [
    "laser verlichting",
    "xenon",
    "xenon verlichting"
]


OPTION_GROUPS = {

    "Matrix LED": [
        "matrix",
        "laserlicht",
        "laser",
        "matrix led"
    ],


    "Bang & Olufsen": [
        "bang",
        "olufsen",
        "b&o"
    ],


    "Head-up display": [
        "head-up",
        "head up",
        "headup"
    ],


    "Massage stoelen": [
        "massage"
    ],


    "Memory stoelen": [
        "memory"
    ],


    "Elektrische stoelen": [
        "elektrisch",
        "electric"
    ],


    "Keyless": [
        "keyless",
        "komfortschlüssel",
        "comfort key"
    ],


    "Adaptieve cruise control": [
        "adaptive cruise",
        "acc",
        "abstandsregelung"
    ],


    "Rijstrookassistent": [
        "lane assist",
        "spurhalte"
    ],


    "Achteruitrijcamera": [
        "rückfahrkamera",
        "kamera"
    ]

}




OPTION_IMPORTANCE = {

    "Matrix LED": 10,

    "Bang & Olufsen": 9,

    "Head-up display": 8,

    "Massage stoelen": 8,

    "Memory stoelen": 7,

    "quattro": 7,

    "Adaptieve cruise control": 7,

    "Virtual cockpit": 6,

    "MMI Navigation Plus": 6,

    "Leder interieur": 6,

    "Achteruitrijcamera": 5,

    "S line": 5,

    "Windschot": 5,

    "Stoelverwarming": 4,

    "Keyless": 4,

    "Elektrische stoelen": 4,

    "Parkeersensoren": 3,

    "Sportstoelen": 3,

    "Klimaautomatik": 3

}




PREMIUM_OPTIONS = {

    "Matrix LED",

    "Bang & Olufsen",

    "Head-up display",

    "Massage stoelen",

    "Memory stoelen",

    "quattro",

    "Adaptieve cruise control",

    "Virtual cockpit",

    "MMI Navigation Plus",

    "Leder interieur",

    "Windschot",

    "S line"

}



def filter_premium_options(options):

    return [
        option
        for option in options
        if option in PREMIUM_OPTIONS
    ]


def get_option_importance(option):

    return OPTION_IMPORTANCE.get(
        option,
        1
    )


def sort_options_by_importance(options):

    return sorted(
        options,
        key=get_option_importance,
        reverse=True
    )


def normalize_option(option):

    if not option:
        return None


    text = option.lower()


    for ignore in IGNORE_OPTIONS:

        if ignore in text:
            return None


    for name, keywords in OPTION_GROUPS.items():

        for keyword in keywords:

            if keyword in text:
                return name


    return option.strip()



def get_normalized_options(car):

    if not car.options_found:
        return []


    result = set()


    for option in car.options_found.split(","):

        normalized = normalize_option(option)

        if normalized:
            result.add(normalized)


    return sorted(result)




def get_weighted_advantages(winner, cars, limit=5):

    winner_options = set(
        get_normalized_options(winner)
    )


    other_options = set()


    for car in cars:

        if car != winner:

            other_options.update(
                get_normalized_options(car)
            )


    advantages = []


    for option in winner_options:

        importance = get_option_importance(
            option
        )


        if importance > 1:

            advantages.append(
                {
                    "option": option,
                    "importance": importance,
                    "shared": option in other_options
                }
            )


    return sorted(
        advantages,
        key=lambda x: x["importance"],
        reverse=True
    )[:limit]


def get_unique_advantages(winner, cars):

    winner_options = set(
        get_normalized_options(winner)
    )


    other_options = set()


    for car in cars:

        if car != winner:

            other_options.update(
                get_normalized_options(car)
            )


    return sorted(
        winner_options - other_options
    )
