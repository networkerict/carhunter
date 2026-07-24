from pathlib import Path

path = Path("templates/car.html")

text = path.read_text()

old = """{% if car.color_detail %}
Fabriekskleur:
{{ car.color_detail }}

<br>
{% endif %}


{% if car.upholstery %}
Bekleding:
{{ car.upholstery }}

<br>
{% endif %}
"""

new = """{% if car.color_detail %}
Fabriekskleur:
{{ car.color_detail }}

<br>
{% endif %}


{% if car.roof_color %}
Dak:
{{ car.roof_color }}

<br>
{% endif %}


{% if car.upholstery %}
Bekleding:
{{ car.upholstery }}

<br>
{% endif %}
"""

if old not in text:
    raise SystemExit(
        "Kleur/interieur blok niet gevonden. Geen wijziging uitgevoerd."
    )

text = text.replace(old, new)

path.write_text(text)

print("car.html roof_color toegevoegd")
