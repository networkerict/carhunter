from pathlib import Path

files = [
    "autohunter.py",
    "config.py",
    "models.py",
    "options.py",
    "pipeline.py",
    "pipeline_report.py",
    "reporting.py",
    "deal_score.py",
    "telegram.py",
    "watchlist.py",
    "watchlist_report.py",
]

for filename in files:

    path = Path(filename)

    if not path.exists():
        print("Niet gevonden:", filename)
        continue

    text = path.read_text()

    old = text

    import re

    text = re.sub(
        r"AutoHunter v[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:-dev)?",
        "AutoHunter v3.0-dev",
        text
    )

    if text != old:
        path.write_text(text)
        print("Aangepast:", filename)
    else:
        print("Geen wijziging:", filename)

print("Versie headers bijgewerkt")
