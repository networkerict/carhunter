import sqlite3


from config import DATABASE

DB = DATABASE


COLORS = {
    "zwart": [
        "schwarz",
        "mythosschwarz",
        "brillantschwarz",
        "akustik-verdeck in schwarz"
    ],

    "grijs": [
        "grau",
        "daytonagrau",
        "quarzgrau",
        "manhattangrau",
        "felsgrau"
    ],

    "wit": [
        "weiß",
        "ibis-weiß",
        "glacierweiß"
    ],

    "blauw": [
        "blau",
        "navarrablau",
        "ascari blau"
    ],

    "groen": [
        "grün",
        "distriktgrün"
    ],

    "rood": [
        "rot",
        "tornadorot"
    ],

    "bruin": [
        "braun",
        "okapi"
    ],

    "zilver": [
        "silber",
        "silbergrau"
    ]
}


COLOR_DETAILS = {

    "Nardo": "Nardo Grau",
    "nardograu": "Nardo Grau",

    "Daytona": "Daytona Grau",
    "daytonagrau": "Daytona Grau",

    "Quarz": "Quarzgrau",
    "quarzgrau": "Quarzgrau",

    "Manhattan": "Manhattangrau",

    "Mythos": "Mythosschwarz",
    "mythosschwarz": "Mythosschwarz",

    "Brillant": "Brillantschwarz",

    "Navarra": "Navarra Blau",

    "Ascari": "Ascari Blau",

    "Ibis": "Ibis Weiß",

    "Glacier": "Glacier Weiß",

    "Tornado": "Tornadorot",

    "District": "Distriktgrün"

}


UPHOLSTERY = {

    "Leder": [
        "leder",
        "lederausstattung",
        "feinnappa",
        "nappa"
    ],

    "Alcantara": [
        "alcantara"
    ],

    "Stof": [
        "stoff"
    ]

}


ROOF_COLORS = {

    "zwart": [
        "verdeck in schwarz",
        "akustik-verdeck in schwarz",
        "stoffverdeck schwarz"
    ],

    "rood": [
        "verdeck rot"
    ],

    "blauw": [
        "verdeck blau"
    ],

    "wagenkleur": [
        "dach in wagenfarbe",
        "verdeck in wagenfarbe"
    ]

}


def detect_color(text):

    if not text:
        return ""

    text = text.lower()

    for color, words in COLORS.items():

        for word in words:

            if word.lower() in text:
                return color

    return ""


def detect_color_detail(text):

    if not text:
        return ""

    text = text.lower()

    for name, detail in COLOR_DETAILS.items():

        if name.lower() in text:
            return detail

    return ""


def detect_upholstery(text):

    if not text:
        return ""

    text = text.lower()

    for material, words in UPHOLSTERY.items():

        for word in words:

            if word in text:
                return material

    return ""


def detect_roof_color(text):

    if not text:
        return ""

    text = text.lower()

    for color, words in ROOF_COLORS.items():

        for word in words:

            if word in text:
                return color

    return ""


def detect_interior_color(text):

    if not text:
        return ""

    text = text.lower()

    markers = [
        "innenfarbe",
        "interieurfarbe",
        "sitze"
    ]

    colors = [
        "schwarz",
        "schwarz/schwarz",
        "rot",
        "braun",
        "beige"
    ]

    for marker in markers:

        pos = text.find(marker)

        if pos != -1:

            section = text[pos:pos+100]

            for color in colors:

                if color in section:
                    return color

    return ""




def detect_gearbox(text):

    if not text:
        return ""

    text = text.lower()

    if "s tronic" in text:
        return "S tronic"

    if "tiptronic" in text:
        return "Tiptronic"

    if "automatik" in text:
        return "Automaat"

    return ""



def detect_body_type(text):

    if not text:
        return ""

    text = text.lower()

    if "cabriolet" in text:
        return "Cabriolet"

    if "avant" in text:
        return "Avant"

    if "limousine" in text:
        return "Limousine"

    return ""



def detect_drive(text):

    if not text:
        return ""

    text = text.lower()

    if "quattro" in text:
        return "quattro"

    if "allrad" in text:
        return "4x4"

    if "vorderrad" in text:
        return "Voorwielaandrijving"

    return ""



def detect_hp(text):

    if not text:
        return 0

    import re

    text = text.lower()


    # Direct vermogen uit kW
    match = re.search(
        r'(\d+)\s*kw',
        text
    )

    if match:

        kw = int(match.group(1))

        return round(
            kw * 1.36
        )


    # Fallback op Audi motorvariant
    if "45 tfsi" in text:
        return 265

    if "40 tfsi" in text:
        return 204

    if "40 tdi" in text:
        return 204


    return 0



conn = sqlite3.connect(DB)
cur = conn.cursor()


cars = cur.execute("""
SELECT id, title, description
FROM cars
""").fetchall()


count = 0


for car_id, title, description in cars:

    text = (
        (title or "")
        + " "
        + (description or "")
    )


    color = detect_color(text)

    color_detail = detect_color_detail(text)

    upholstery = detect_upholstery(text)

    roof_color = detect_roof_color(text)

    interior_color = detect_interior_color(text)

    gearbox = detect_gearbox(text)

    body_type = detect_body_type(text)

    drive = detect_drive(text)

    hp = detect_hp(text)


    cur.execute("""
    UPDATE cars
    SET
        color=?,
        color_detail=?,
        upholstery=?,
        interior_color=?,
        roof_color=?,
        gearbox=?,
        body_type=?,
        hp=?,
        drive=?
    WHERE id=?
    """,
    (
        color,
        color_detail,
        upholstery,
        interior_color,
        roof_color,
        gearbox,
        body_type,
        hp,
        drive,
        car_id
    ))

    count += 1


conn.commit()
conn.close()


print(
    f"Features bijgewerkt voor {count} auto's"
)
