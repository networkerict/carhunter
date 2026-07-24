from pathlib import Path

path = Path("templates/debug_score.html")

text = path.read_text()

old = """<h2>
Premium score: {{premium_score}}
</h2>
"""

new = """<h2>
Premium score: {{premium_score}}
</h2>

<ul>

{% for item in premium_breakdown %}

<li>
+{{item.points}} {{item.reason}}
</li>

{% endfor %}

</ul>
"""

if old not in text:
    raise SystemExit(
        "Premium score blok niet gevonden. Geen wijziging uitgevoerd."
    )

text = text.replace(old, new)

path.write_text(text)

print("debug_score.html premium breakdown toegevoegd")
