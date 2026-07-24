from pathlib import Path

file = Path("dashboard_data.py")

text = file.read_text()

old = """        car.personal_score >= 100
        or car.final_score >= 85
"""

new = """        car.watchlist_match == 1
        and (
            car.personal_score >= 70
            or car.deal_score >= 40
        )
"""

if old not in text:
    raise SystemExit(
        "Dashboard interesting logic niet gevonden. Geen wijziging uitgevoerd"
    )

text = text.replace(old, new)

file.write_text(text)

print("dashboard_data.py aangepast naar watchlist logica")
