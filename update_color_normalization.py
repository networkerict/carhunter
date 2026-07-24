from pathlib import Path

file = Path("scraper.py")

text = file.read_text()


# voeg extra cleanup toe na lower()
old = """    color = color.lower()
"""

new = """    color = color.lower().strip()

    # AutoScout kleurcodes opschonen
    color = color.replace("0e ", "")
    color = color.replace("0e-", "")
"""


if old not in text:
    raise SystemExit(
        "Cleanup blok niet gevonden. scraper.py NIET aangepast"
    )

text = text.replace(
    old,
    new,
    1
)


# uitbreiden mapping
old = '''        "quarzgrau":
            "Quarz Grau",

        "mythosschwarz":
            "Mythosschwarz",
'''

new = '''        "quarzgrau":
            "Quarz Grau",

        "chronosgrau":
            "Chronos Grau",

        "daytonagrau perleffekt":
            "Daytona Grau",

        "mythosschwarz":
            "Mythosschwarz",
'''


if old not in text:
    raise SystemExit(
        "Mapping blok niet gevonden. scraper.py NIET aangepast"
    )


text = text.replace(
    old,
    new,
    1
)


file.write_text(text)

print("kleur normalisatie bijgewerkt")
