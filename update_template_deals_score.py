from pathlib import Path

file = Path("templates/deals.html")

text = file.read_text()

old = """<p>

⭐ Auto score:

<strong>
{{car.final_score}}
</strong>

</p>
"""

new = """<p>

❤️ Persoonlijke score:

<strong>
{{car.personal_score}}
</strong>

</p>

<p>

⭐ Basis score:

<strong>
{{car.final_score}}
</strong>

</p>
"""

if old not in text:
    raise SystemExit(
        "deals score blok niet gevonden. Geen wijziging uitgevoerd"
    )

text = text.replace(old, new)

file.write_text(text)

print("deals.html aangepast")
