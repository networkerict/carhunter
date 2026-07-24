from pathlib import Path

files = [
    "templates/car.html",
    "templates/ranking.html",
    "templates/index.html",
    "templates/deals.html",
]

old = "car.options_found.split(\",\")"
new = "car.options_found.split(\",\")|sort"

for filename in files:

    path = Path(filename)

    if not path.exists():
        continue

    text = path.read_text()
    original = text

    text = text.replace(old, new)

    if text != original:
        path.write_text(text)
        print("Aangepast:", filename)
    else:
        print("Geen wijziging:", filename)

print("Opties sortering bijgewerkt")
