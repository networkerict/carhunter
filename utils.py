import re


def extract_year(text):

    if not text:
        return None

    patterns = [
        # datum formaat 04-2023 / 10-2009
        r"\b\d{2}[-/.](20\d{2})\b",

        # losse jaren
        r"\b(20\d{2})\b",

        # Duitse velden
        r"Erstzulassung[^0-9]*(20\d{2})",
        r"EZ[^0-9]*(20\d{2})",
        r"Baujahr[^0-9]*(20\d{2})",
    ]

    for p in patterns:

        m = re.search(
            p,
            text,
            re.IGNORECASE
        )

        if m:
            year = int(m.group(1))

            if 2000 <= year <= 2026:
                return str(year)

    return None

def normalize_year(value):

    if not value:
        return None

    if isinstance(value, dict):
        return str(value.get("year"))

    if isinstance(value, str):

        m = re.search(r"(20[1-2][0-9])", value)

        if m:
            return m.group(1)

    return None


def create_fingerprint(car):

    return "|".join(
        [
            str(car.get("make", "")),
            str(car.get("model", "")),
            str(car.get("motor", "")),
            str(car.get("km", "")),
            str(car.get("year", ""))
        ]
    )
