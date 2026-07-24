from pathlib import Path

path = Path("models.py")

text = path.read_text()

old = """        self.upholstery = row[26]
        self.interior_color = row[27]

        self.gearbox = row[28]
"""

new = """        self.upholstery = row[26]
        self.interior_color = row[27]
        self.roof_color = row[37]

        self.gearbox = row[28]
"""

if old not in text:
    raise SystemExit(
        "Model blok niet gevonden. Geen wijziging uitgevoerd."
    )

text = text.replace(old, new)

path.write_text(text)

print("models.py roof_color toegevoegd")
