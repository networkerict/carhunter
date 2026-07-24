from watchlist import WATCHLIST


def matches_watchlist(car):

    if (car.price or 0) > WATCHLIST["price_max"]:
        return False

    try:
        year = int(str(car.year)[-4:])
    except:
        year = 0

    if year < WATCHLIST["year_min"]:
        return False

    if (car.km or 0) > WATCHLIST["km_max"]:
        return False

    def normalize_watchlist_color(color):

        color = (color or "").lower()


        if any(x in color for x in [
            "schwarz",
            "black",
            "zwart",
            "mythosschwarz",
            "brillantschwarz"
        ]):
            return "zwart"


        if any(x in color for x in [
            "grau",
            "grey",
            "grijs",
            "daytona",
            "manhattan",
            "quarz"
        ]):
            return "grijs"


        return color


    color_source = " ".join([
        car.color or "",
        car.color_detail or ""
    ])

    color = normalize_watchlist_color(
        color_source
    )


    if color not in [
        "zwart",
        "grijs"
    ]:
        return False

    options_found = car.options_found or ""

    for option in WATCHLIST["required_options"]:
        if option not in options_found:
            return False

    return True

def calculate_personal_score(car):

    if not matches_watchlist(car):
        return 0


    score = car.final_score


    for option, bonus in WATCHLIST["preferred_options"].items():

        if option in (car.options_found or ""):
            score += bonus


    return score
