#!/usr/bin/env python3

"""
AutoHunter v2.9
Recommendation report
"""

import database
import recommendation_engine


def show_recommendation():

    cars = database.get_recommendation_candidates(5)


    if len(cars) < 2:

        print(
            "Niet genoeg auto's beschikbaar"
        )

        return


    result = recommendation_engine.generate_recommendation(
        cars
    )


    winner = result["winner"]
    value = result["value_choice"]


    print()
    print("================================")
    print(" AutoHunter Recommendation")
    print("================================")
    print()


    print("🏆 BESTE KEUZE")
    print()

    print(winner.title)
    print(f"ID: {winner.id}")
    print(f"Prijs: €{winner.price}")
    print(f"Score: ⭐{winner.final_score}")

    print()

    print("Waarom:")

    for reason in result["recommendation_reasons"]:

        print(
            "✓",
            reason
        )


    if value and value.id != winner.id:

        print()
        print("💰 BESTE WAARDE")
        print()

        print(value.title)
        print(f"ID: {value.id}")
        print(f"Prijs: €{value.price}")
        print(f"Score: ⭐{value.final_score}")

        print()

        print("Afweging:")
        print(
            f"€{result['price_difference']} prijsverschil"
        )

        print(
            f"{result['score_difference']} punten scoreverschil"
        )


if __name__ == "__main__":

    show_recommendation()
