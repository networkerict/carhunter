from pathlib import Path

path = Path("premium.py")

text = path.read_text()

old = """def analyze_premium(car):

    text = (
        (car.title or "")
        + " "
        + (car.description or "")
    ).lower()

    score = 0


    for option, data in PREMIUM_POINTS.items():

        for alias in data["aliases"]:

            if alias.lower() in text:
                score += data["points"]
                break


    return score
"""

new = """def analyze_premium(car, explain=False):

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
"""

if old not in text:
    raise SystemExit(
        "Oude functie niet gevonden. Geen wijziging uitgevoerd."
    )

text = text.replace(old, new)

path.write_text(text)

print("premium.py bijgewerkt")
