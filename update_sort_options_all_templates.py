from pathlib import Path

changes = {
    "templates/dashboard.html": [
        (
            '{% for option in car.options_found.split(",") %}',
            '{% for option in car.options_found.split(",")|sort %}'
        )
    ],

    "templates/index.html": [
        (
            'car.options_found.split(",")|sort[:5]',
            'car.options_found.split(",")|sort'
        )
    ]
}


for filename, replacements in changes.items():

    path = Path(filename)

    if not path.exists():
        print("Niet gevonden:", filename)
        continue

    text = path.read_text()
    old_text = text

    for old, new in replacements:
        text = text.replace(old, new)

    if text != old_text:
        path.write_text(text)
        print("Aangepast:", filename)
    else:
        print("Geen wijziging:", filename)

print("Optie sortering templates bijgewerkt")
