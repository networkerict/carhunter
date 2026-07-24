from pathlib import Path

file = Path("autohunter.py")

text = file.read_text()

old = """def is_interesting_car(car):

    return (
        car.personal_score >= 100
        or car.deal_score >= 40
        or car.final_score >= 85
    )
"""

new = """def is_interesting_car(car):

    if car.watchlist_match != 1:
        return False

    return (
        car.personal_score >= 70
        or car.deal_score >= 40
    )
"""

if old not in text:
    raise SystemExit(
        "is_interesting_car blok niet gevonden. Geen wijziging uitgevoerd"
    )

text = text.replace(old, new)

file.write_text(text)

print("is_interesting_car aangepast naar watchlist gebaseerde logica")
