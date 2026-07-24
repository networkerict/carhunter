from pathlib import Path

path = Path("templates/debug_score.html")

text = path.read_text()

old = """<h2>
Options score: {{options_score}}
</h2>


<ul>

{% for option in options %}

<li>
✓ {{option}}
</li>

{% endfor %}

</ul>
"""

new = """<h2>
Options score: {{options_score}}
</h2>


<ul>

{% for item in option_breakdown %}

<li>
+{{item.points}} {{item.option}}
</li>

{% endfor %}

</ul>
"""

if old not in text:
    raise SystemExit(
        "Options score blok niet gevonden. Geen wijziging uitgevoerd."
    )

text = text.replace(old, new)

path.write_text(text)

print("debug_score.html options breakdown toegevoegd")
