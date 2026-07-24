from pathlib import Path

path = Path("webapp.py")

text = path.read_text()

old = """    premium_score = premium.analyze_premium(car)


    return render_template(
        "debug_score.html",
        car=car,
        car_score=car_score,
        car_breakdown=car_breakdown,
        value_score=value_score,
        value_breakdown=value_breakdown,
        options=found,
        options_score=option_score,
        premium_score=premium_score
    )
"""

new = """    premium_score, premium_breakdown = premium.analyze_premium(
        car,
        explain=True
    )


    return render_template(
        "debug_score.html",
        car=car,
        car_score=car_score,
        car_breakdown=car_breakdown,
        value_score=value_score,
        value_breakdown=value_breakdown,
        options=found,
        options_score=option_score,
        premium_score=premium_score,
        premium_breakdown=premium_breakdown
    )
"""

if old not in text:
    raise SystemExit(
        "Oude webapp score sectie niet gevonden. Geen wijziging uitgevoerd."
    )

text = text.replace(old, new)

path.write_text(text)

print("webapp.py premium breakdown toegevoegd")
