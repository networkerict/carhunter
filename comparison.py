#!/usr/bin/env python3

"""
AutoHunter v2.9
Vehicle comparison helpers
"""


def get_all_options(cars):

    options = set()


    for car in cars:

        if not car.options_found:
            continue


        for option in car.options_found.split(","):

            option = option.strip()

            if option:
                options.add(option)


    return sorted(options)



def has_option(car, option):

    if not car.options_found:
        return False


    car_options = [
        x.strip()
        for x in car.options_found.split(",")
    ]


    return option in car_options
