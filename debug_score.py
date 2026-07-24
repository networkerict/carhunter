"""
AutoHunter v2.4
Score explanation
"""

import scoring
import options
import premium

def explain_score(car):

    print()
    print("==============================")
    print(" SCORE EXPLANATION")
    print("==============================")
    print()


    print(car.title)
    print(
        f"Price: €{car.price}"
    )
    print(
        f"KM: {car.km}"
    )
    print(
        f"Year: {car.year}"
    )

    print()


    #
    # CAR SCORE
    #
    car_score, car_breakdown = scoring.calculate_car_score(
        car,
        explain=True
    )

    print("------------------------------")
    print("CAR SCORE")
    print("------------------------------")

    for item in car_breakdown:
        print(
            f"+{item['points']:>2}  {item['reason']}"
        )

    print(
        f"TOTAL: {car_score}"
    )


    print()


    #
    # VALUE SCORE
    #
    value_score, value_breakdown = scoring.calculate_value_score(
        car,
        explain=True
    )


    print("------------------------------")
    print("VALUE SCORE")
    print("------------------------------")


    for item in value_breakdown:
        print(
            f"+{item['points']:>2}  {item['reason']}"
        )


    print(
        f"TOTAL: {value_score}"
    )


    print()


    #
    # OPTIONS SCORE
    #
    found, option_score = options.analyze_options(
        car
    )

    option_breakdown = []

    for option in found:
        points = options.OPTION_POINTS.get(
            option,
            {}
        ).get(
            "points",
            0
        )

        option_breakdown.append(
            {
                "option": option,
                "points": points
            }
        )

    print("------------------------------")
    print("OPTIONS SCORE")
    print("------------------------------")


    for item in option_breakdown:
        print(
            f"+{item['points']:>2}  {item['option']}"
        )


    print(
        f"TOTAL: {option_score}"
    )


    print()


    #
    # PREMIUM SCORE
    #
    premium_score = premium.analyze_premium(car)

    print()

    print("------------------------------")
    print("PREMIUM SCORE")
    print("------------------------------")

    premium_text = (
        (car.title or "")
        + " "
        + (car.description or "")
    ).lower()


    for name, data in premium.PREMIUM_POINTS.items():

        for alias in data["aliases"]:

            if alias.lower() in premium_text:

                print(
                    f"+{data['points']:>2}  {name}"
                )

                break


    print(
        f"TOTAL: {premium_score}"
    )


    #
    # FINAL
    #
    print("------------------------------")
    print("FINAL SCORE")
    print("------------------------------")


    print(
        f"Car score:     {car_score}"
    )

    print(
        f"Value score:   {value_score}"
    )

    print(
        f"Options score: {option_score}"
    )

    print()

    print("------------------------------")
    print("FINAL SCORE CALCULATION")
    print("------------------------------")


    car_weight = car_score * 0.35

    value_weight = value_score * 0.25


    MAX_OPTION_SCORE = options.OPTION_MAX_REALISTIC

    options_weight = (
        option_score / MAX_OPTION_SCORE
    ) * 25

    premium_weight = premium_score

    raw_total = (
        car_weight
        +
        value_weight
        +
        options_weight
        +
        premium_weight
    )


    print(
        f"Car:     {car_score} x 0.35 = {car_weight:.1f}"
    )

    print(
        f"Value:   {value_score} x 0.25 = {value_weight:.1f}"
    )

    print(
        f"Options: {option_score}/{MAX_OPTION_SCORE} x 25 = {options_weight:.1f}"
    )

    print(
        f"Premium: {premium_score}"
    )


    print()

    print(
        f"RAW TOTAL: {raw_total:.1f}"
    )

    print(
        f"FINAL SCORE: {int(raw_total)}"
    )

    print()
