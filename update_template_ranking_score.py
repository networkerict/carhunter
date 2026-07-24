from pathlib import Path

file = Path("templates/ranking.html")

text = file.read_text()

old = """<div class="score-badge">
Score {{ car.final_score }}
</div>
"""

new = """<div class="score-badge">
❤️ Persoonlijke score {{ car.personal_score }}
<br>
⭐ Basis score {{ car.final_score }}
</div>
"""

if old not in text:
    raise SystemExit(
        "ranking score blok niet gevonden. Geen wijziging uitgevoerd"
    )

text = text.replace(old, new)

file.write_text(text)

print("ranking.html aangepast")
