from pathlib import Path

file = Path("scraper.py")

text = file.read_text()


old = """        body_color_original = vehicle.get(
            "bodyColorOriginal"
        )
"""


new = """        body_color_original = normalize_color_detail(
            vehicle.get(
                "bodyColorOriginal"
            )
        )
"""


if old not in text:
    raise SystemExit(
        "body_color_original blok niet gevonden. scraper.py NIET aangepast"
    )


text = text.replace(
    old,
    new,
    1
)


file.write_text(text)

print(
    "fetch_car_details kleur normalisatie toegevoegd"
)
