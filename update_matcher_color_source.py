from pathlib import Path

file = Path("matcher.py")

text = file.read_text()

old = """    color = normalize_watchlist_color(
        car.color_detail or car.color
    )
"""

new = """    color_source = " ".join([
        car.color or "",
        car.color_detail or ""
    ])

    color = normalize_watchlist_color(
        color_source
    )
"""

if old not in text:
    raise SystemExit(
        "Matcher kleurblok niet gevonden. Geen wijziging uitgevoerd"
    )

text = text.replace(old, new)

file.write_text(text)

print("matcher.py kleurbron aangepast")
