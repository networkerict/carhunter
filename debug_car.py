"""
AutoHunter v2.4
Vehicle debug display
"""

import debug


def show_car(car):

    if car is None:
        debug.warning(
            "No vehicle data available"
        )
        return


    print()
    print("==============================")
    print(" AutoHunter DEBUG")
    print("==============================")
    print()


    print("ID:")
    print(car.id)

    print()

    print("Vehicle:")
    print(car.title)

    print()

    print("Price:")
    print(f"€ {car.price:,}".replace(",", "."))

    print()

    print("Mileage:")
    print(f"{car.km:,} km".replace(",", "."))

    print()

    print("Year:")
    print(car.year)

    print()

    print("Scores:")
    print(f"Car score:      {car.car_score}")
    print(f"Value score:    {car.value_score}")
    print(f"Options score:  {car.options_score}")
    print(f"Final score:    {car.final_score}")

    print()

    print("Options:")
    print(car.options_found)

    print()

    print("Description:")
    print("------------------------------")

    if car.description:

        print(
            f"Length: {len(car.description)} characters"
        )

        print()

        preview = car.description[:300]

        print("Preview:")
        print(preview)

    else:

        print("No description available")

    print("------------------------------")

    print()

    print("Recommendation:")
    print(car.recommendation)

    print()

    print("URL:")
    print(car.url)

    print()
