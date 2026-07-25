#!/usr/bin/env python3

"""
AutoHunter v3.0-dev
Ranking & Reporting
"""

import database


def print_line():
    print("--------------------------------")


def show_today(limit=10):

    cars = database.get_todays_cars(limit)

    print()
    print("================================")
    print(" AUTOHUNTER NEW TODAY")
    print("================================")
    print()

    if not cars:
        print("Geen nieuwe auto's gevonden vandaag")
        return

    print(
        f"Nieuwe auto's: {len(cars)}"
    )

    print()

    best = cars[0]

    print("Beste match:")
    print(
        f"{best.title}"
    )
    print(
        f"Score: {best.final_score}"
    )
    print(
        f"Prijs: €{best.price}"
    )

    print()
    print("--------------------------------")
    print()

    print("Top overzicht:")
    print()

    for index, car in enumerate(cars, 1):

        print(
            f"{index}. {car.title}"
        )

        print(
            f"   Score: {car.final_score}"
        )

        print(
            f"   Prijs: €{car.price}"
        )

        print()

    print("================================")


def show_ranking(limit=10):

    cars = database.get_ranked_cars(limit)

    print()
    print("================================")
    print(f" AUTOHUNTER RANKING TOP {limit}")
    print("================================")
    print()

    if not cars:
        print("Geen auto's gevonden")
        return


    for index, car in enumerate(cars, 1):

        print(f"#{index} {car.title}")

        print_line()

        print(
            f"Score:    {car.final_score}"
        )

        print(
            f"Prijs:    €{car.price}"
        )

        print(
            f"Jaar:     {car.year}"
        )

        print(
            f"KM:       {car.km}"
        )

        print()

        print(
            f"Car:      {car.car_score}"
        )

        print(
            f"Value:    {car.value_score}"
        )

        print(
            f"Options:  {car.options_score}"
        )

        print(
            f"Premium:  {car.premium_score}"
        )

        print()

        if car.options_found:

            print("Opties:")

            options = car.options_found.split(",")

            for option in options:
                print(
                    f"✓ {option.strip()}"
                )

        print()
        print_line()
        print()


def generate_report():

    cars = database.get_ranked_cars(10)

    filename = (
        "/opt/carhunter/"
        "reports/"
        "ranking_report.txt"
    )

    import os

    os.makedirs(
        "/opt/carhunter/reports",
        exist_ok=True
    )

    with open(filename, "w") as f:

        f.write(
            "AUTOHUNTER RANKING REPORT\n"
        )

        f.write(
            "=========================\n\n"
        )


        for index, car in enumerate(cars, 1):

            f.write(
                f"#{index} {car.title}\n"
            )

            f.write(
                "--------------------------------\n"
            )

            f.write(
                "\nScore:\n"
            )

            f.write(
                f"Final score : {car.final_score}\n"
            )

            f.write(
                f"Car         : {car.car_score}\n"
            )

            f.write(
                f"Value       : {car.value_score}\n"
            )

            f.write(
                f"Options     : {car.options_score}\n"
            )

            f.write(
                f"Premium     : {car.premium_score}\n"
            )


            f.write(
                "\nAuto:\n"
            )

            f.write(
                f"Prijs       : €{car.price}\n"
            )

            f.write(
                f"Jaar        : {car.year}\n"
            )

            f.write(
                f"KM          : {car.km}\n"
            )


            if car.options_found:

                f.write(
                    "\nOpties:\n"
                )

                for option in car.options_found.split(","):

                    f.write(
                        f"✓ {option.strip()}\n"
                    )


            f.write(
                "\nURL:\n"
            )

            f.write(
                f"{car.url}\n"
            )


            f.write(
                "\n"
                "--------------------------------\n\n"
            )


    print(
        f"Report created: {filename}"
    )
