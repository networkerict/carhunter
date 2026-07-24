from pathlib import Path
import re

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
    "dashboard_data.py",
    "recommendation.py",
]

for filename in files:

    path = Path(filename)

    if not path.exists():
        print("Niet gevonden:", filename)
        continue

    text = path.read_text()
    old = text

    text = re.sub(
        r"AutoHunter v[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:-dev)?",
        "AutoHunter v2.9-dev",
        text
    )

    if filename == "config.py":
        text = text.replace(
            'VERSION = "2.8"',
            'VERSION = "2.9-dev"'
        )

    if text != old:
        path.write_text(text)
        print("Aangepast:", filename)
    else:
        print("Geen wijziging:", filename)

print("v2.9-dev versie headers bijgewerkt")
