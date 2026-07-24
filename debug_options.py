def explain_options(car):

    print()
    print("==============================")
    print(" OPTION DEBUG")
    print("==============================")
    print()

    print("Vehicle:")
    print(car.title)

    print()

    if not car.description:

        print("No description available")
        return

    description = car.description.lower()

    print(
        "Description length:"
    )

    print(
        f"{len(car.description)} characters"
    )

    print()
    print("Checking options:")
    print()


    options = {

        "quattro": [
            "quattro"
        ],

        "Matrix LED": [
            "matrix led",
            "matrixlicht"
        ],

        "Leder interieur": [
            "leder",
            "lederausstattung"
        ],

        "Sportstoelen": [
            "sportsitze",
            "sportstoelen"
        ],

        "Stoelverwarming": [
            "sitzheizung",
            "stoelverwarming"
        ],

        "MMI Navigation Plus": [
            "mmi navigation plus",
            "mmi plus"
        ]

    }


    for option, keywords in options.items():

        found = False

        match = ""

        for keyword in keywords:

            if keyword in description:

                found = True
                match = keyword
                break


        if found:

            print(
                f"✓ {option}"
            )

            print(
                f"  Matched: {match}"
            )

        else:

            print(
                f"✗ {option}"
            )

        print()
