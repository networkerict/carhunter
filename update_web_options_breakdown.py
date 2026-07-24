from pathlib import Path

path = Path("webapp.py")

text = path.read_text()

old = """    found, option_score = options.analyze_options(car)


    premium_score, premium_breakdown = premium.analyze_premium(
        car,
        explain=True
    )
"""

new = """    found, option_score, option_breakdown = options.analyze_options(
        car,
        explain=True
    )


    premium_score, premium_breakdown = premium.analyze_premium(
        car,
        explain=True
    )
"""

if old not in text:
    raise SystemExit(
        "Options analyse blok niet gevonden. Geen wijziging uitgevoerd."
    )


text = text.replace(old, new)


old2 = """        options=found,
        options_score=option_score,
        premium_score=premium_score,
        premium_breakdown=premium_breakdown
"""

new2 = """        options=found,
        options_score=option_score,
        option_breakdown=option_breakdown,
        premium_score=premium_score,
        premium_breakdown=premium_breakdown
"""


if old2 not in text:
    raise SystemExit(
        "Template parameters niet gevonden. Geen wijziging uitgevoerd."
    )


text = text.replace(old2, new2)


path.write_text(text)

print("webapp.py options breakdown toegevoegd")
