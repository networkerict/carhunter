#!/usr/bin/env python3

import re
import requests
import json
import debug
import database
from utils import (
    extract_year,
    normalize_year,
    create_fingerprint
)

BASE_URL = (
    "https://www.autoscout24.de/lst/audi/a5?"
    "atype=C&page={}"
)

PAGES = 100


def parse_km(value):

    if not value:
        return 0

    try:
        return int(
            str(value)
            .replace(".", "")
            .replace(" km", "")
            .strip()
        )

    except:
        return 0

def safe_text(value):

    if value is None:
        return ""

    return str(value)


def http_get(url):

    headers = {
        "User-Agent":
        "Mozilla/5.0"
    }

    r = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    return r.text



def extract_json(html):

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html
    )

    if not match:
        return None

    return json.loads(
        match.group(1)
    )

def get_listing_details(data):

    try:

        page = (
            data
            .get("props", {})
            .get("pageProps", {})
        )

        # normale AutoScout24 advertentie
        listing = page.get(
            "listingDetails"
        )

        if listing:
            return listing


        # AutoScout24 SMYLE
        smyle = (
            page
            .get("properData", {})
            .get("carDetails")
        )

        if smyle:
            return smyle


        return None


    except Exception as e:

        debug.warning(
            f"Listing details error: {e}"
        )

        return None

def get_detail_listing(url):

    try:

        html = http_get(url)

        data = extract_json(html)

        import json

        with open("/tmp/autoscout_debug.json", "w") as f:
            json.dump(data, f, indent=2)


        if not data:
            return None


        return get_listing_details(data)

    except Exception as e:

        print(
            "Detail fout:",
            e
        )

        return None



def fetch_description(url):

    try:

        html = http_get(url)

        data = extract_json(html)

        if not data:
            return ""


        listing = get_listing_details(data)

        if not listing:
            debug.warning(
                f"No listingDetails found: {url}"
            )
            return ""

        vehicle = listing.get(
            "vehicle",
            {}
        )


        candidates = [
            listing.get("description"),
            vehicle.get("marketingDescription"),
            vehicle.get("description"),
            vehicle.get("descriptionText"),
            vehicle.get("sellerDescription"),
        ]

        for value in candidates:

            text = safe_text(value)

            if len(text) > 20:
                return text


        return ""


    except Exception as e:

        debug.warning(
            f"Description error: {e}"
        )

        return ""



def fetch_car_details(url):

    try:

        html = http_get(url)

        data = extract_json(html)

        if not data:
            return None


        cd = get_listing_details(data)

        if not cd:
            debug.warning(
                f"No listingDetails found: {url}"
            )
            return None

        vehicle = cd.get(
            "vehicle",
            {}
        )


        options = []

        equipment = vehicle.get(
            "equipment",
            {}
        )


        for category, items in equipment.items():

            for item in items:

                option = item.get("id")

                if option:
                    options.append(option)

        body_color = vehicle.get(
            "bodyColor"
        )

        body_color_original = normalize_color_detail(
            vehicle.get(
                "bodyColorOriginal"
            )
        )

        return {
            "id": cd.get("id"),

            "make": vehicle.get(
                "make"
            ),

            "model": vehicle.get(
                "model"
            ),

            "title": " ".join(
                x for x in [
                    vehicle.get("make"),
                    vehicle.get("model"),
                    vehicle.get("motorTypeName")
                ]
                if x
            ),

            "motor": vehicle.get(
                "motorTypeName"
            ),

            "price": (
                cd.get("price", {})
                .get("value", {})
                .get("raw")
            ),

            "km": parse_km(
                vehicle.get(
                    "mileageInKmRaw"
                )
            ),

            "year": (
                normalize_year(
                    vehicle.get("firstRegistrationDate")
                )
                or extract_year(
                    cd.get("description", "")
                )
                or extract_year(
                    cd.get("modelVersion", "")
                )
            ),

            "url": url,

            "color": body_color,

            "color_detail": body_color_original,

            "hp": vehicle.get(
                "rawPowerInHp"
            ),

            "drive": vehicle.get(
                "driveTrain"
            ),

            "options": options,

            "upholstery": vehicle.get(
                "upholstery"
            ),

            "interior_color": vehicle.get(
                "upholsteryColor"
            ),

            "gearbox": vehicle.get(
                "transmissionType"
            ),

            "body_type": vehicle.get(
                "bodyType"
            ),

            "fingerprint": create_fingerprint({
                "make": cd.get("make"),
                "model": cd.get("model"),
                "motor": cd.get("modelVersion"),
                "km": vehicle.get("mileageInKmRaw"),
                "year": (
                    normalize_year(
                       vehicle.get("firstRegistrationDate")
                    )
                )
            })

        }


    except Exception as e:

        print(
            "Car details fout:",
            e
        )

        return None

def fetch_page(page):

    url = BASE_URL.format(page)

    return http_get(url)



def parse_page(html):

    data = extract_json(html)

    if not data:
        return []


    try:

        return (
            data["props"]
            ["pageProps"]
            ["listings"]
        )

    except Exception as e:

        debug.warning(
            f"Parse listings error: {e}"
        )

        return []



def create_fingerprint(car):

    v = car.get(
        "vehicle",
        {}
    )

    make = (
        car.get("make")
        or v.get("make")
        or ""
    )

    model = (
        car.get("model")
        or v.get("model")
        or ""
    )

    motor = (
        car.get("motor")
        or v.get("motorTypeName")
        or ""
    )

    km = (
        car.get("km")
        or v.get("mileageInKm")
        or ""
    )

    year = (
        car.get("year")
        or car.get(
            "tracking",
            {}
        ).get(
            "firstRegistration",
            ""
        )
        or ""
    )

    return "|".join(
        [
            str(make),
            str(model),
            str(motor),
            str(km),
            str(year)
        ]
    )


def normalize_color(color):

    if not color:
        return ""

    mapping = {
        "blau": "blauw",
        "blue": "blauw",

        "grau": "grijs",
        "grey": "grijs",

        "schwarz": "zwart",
        "black": "zwart",

        "weiß": "wit",
        "weiss": "wit",
        "white": "wit",

        "grün": "groen",
        "green": "groen",

        "rot": "rood",
        "red": "rood",

        "braun": "bruin",
        "brown": "bruin",

        "silber": "zilver",
        "silver": "zilver",
    }

    return mapping.get(
        color.lower(),
        color.lower()
    )



def normalize_color_detail(color):

    if not color:
        return ""

    color = color.lower().strip()

    # AutoScout kleurcodes opschonen
    color = color.replace("0e ", "")
    color = color.replace("0e-", "")


    mapping = {

        "navarrablau":
            "Navarra Blau",

        "ascari blau":
            "Ascari Blau",

        "daytonagrau":
            "Daytona Grau",

        "manhattangrau":
            "Manhattan Grau",

        "quarzgrau":
            "Quarz Grau",

        "chronosgrau":
            "Chronos Grau",

        "daytonagrau perleffekt":
            "Daytona Grau",

        "mythosschwarz":
            "Mythosschwarz",

        "brillantschwarz":
            "Brillantschwarz",

        "ibis weiß":
            "Ibis Weiß",

        "glacierweiß":
            "Glacier Weiß",

        "tornadorot":
            "Tornado Rot",
    }


    for key, value in mapping.items():

        if key in color:

            return value


    return color.title()




def extract_color_fallback(car):

    detail = car.get(
        "detail",
        {}
    )

    vehicle = car.get(
        "vehicle",
        {}
    )

    color = detail.get(
        "color",
        ""
    )

    color_detail = detail.get(
        "color_detail",
        ""
    )


    if not color:
        color = vehicle.get(
            "bodyColor",
            ""
        )


    if not color_detail:
        color_detail = vehicle.get(
            "bodyColorOriginal",
            ""
        )


    search_text = " ".join(
        [
            str(car.get("url", "")),
            str(car.get("title", "")),
        ]
    ).lower()


    url_colors = {
        "schwarz": "zwart",
        "schwarz": "zwart",
        "weiss": "wit",
        "weiß": "wit",
        "gruen": "groen",
        "grün": "groen",
        "grau": "grijs",
        "silber": "zilver",
        "rot": "rood",
        "blau": "blauw",
    }


    if not color:

        for key, value in url_colors.items():

            if key in search_text:
                color = value
                break


    return {
        "color": color,
        "color_detail": color_detail,
    }



def normalize_car(car):

    v = car["vehicle"]

    options = []

    equipment = {}

    if car.get("detail"):
        equipment = car["detail"].get(
            "options",
            []
        )

    if isinstance(equipment, list):

        options = equipment

    return {

        "id":
            car.get("id"),

        "fingerprint":
            create_fingerprint(car),

        "title":
            " ".join(
                x for x in [
                    v.get("make"),
                    v.get("model"),
                    v.get("motorTypeName")
                ]
                if x
            ),

        "price":
            car.get(
                "price",
                {}
            )
            .get(
                "priceRaw"
            ),

        "km":
            parse_km(
                v.get(
                    "mileageInKm"
                )
            ),

        "year":
            normalize_year(
                car.get(
                    "tracking",
                    {}
                ).get(
                    "firstRegistration",
                    ""
                )
            ),

        "color":
            normalize_color(
                extract_color_fallback(car).get(
                    "color",
                    ""
                )
            ),

        "color_detail":
            normalize_color_detail(
                extract_color_fallback(car).get(
                    "color_detail",
                    ""
                )
            ),

        "upholstery":
            car.get(
                "detail",
                {}
            ).get(
                "upholstery",
                ""
            ),

        "interior_color":
            car.get(
                "detail",
                {}
            ).get(
                "interior_color",
                ""
            ),

        "gearbox":
            car.get(
                "detail",
                {}
            ).get(
                "gearbox",
                ""
            ),

        "body_type":
            car.get(
                "detail",
                {}
            ).get(
                "body_type",
                ""
            ),

        "hp":
            car.get(
                "detail",
                {}
            ).get(
                "hp",
                ""
            ),

        "drive":
            car.get(
                "detail",
                {}
            ).get(
                "drive",
                ""
            ),

        "url":
            "https://www.autoscout24.de"
            +
            car.get(
                "url",
                ""
            )
    }



def run_scraper():

    cars = {}

    for page in range(
        1,
        PAGES + 1
    ):

        debug.info(
            f"Scraping page {page}/{PAGES}"
        )


        html = fetch_page(page)


        for car in parse_page(html):

            v = car.get(
                "vehicle",
                {}
            )


            if v.get(
                "variant"
            ) != "Cabriolet":

                continue


            fingerprint = create_fingerprint(
                car
            )

            car["fingerprint"] = fingerprint


            cars[fingerprint] = car


    debug.info(
        f"Cars found: {len(cars)}"
    )

    new_cars = 0

    active_fingerprints = []

    for car in cars.values():

        fingerprint = car.get("fingerprint")

        if fingerprint:
            active_fingerprints.append(fingerprint)

        url = (
            "https://www.autoscout24.de"
            +
            car.get("url","")
        )

        debug.info(
            f"Fetching details: {url}"
        )

        if database.car_exists(
            car.get("fingerprint")
        ):
            debug.info(
                "Existing car - skipping details"
            )

        else:
            debug.info(
                "New car - fetching details"
            )

            details = fetch_car_details(url)

            if details:
                car["detail"] = details

        result = database.save_car(
            normalize_car(car)
        )

        if result:
            new_cars += 1

    not_available_anymore = database.mark_missing_cars_sold(active_fingerprints)

    return new_cars, not_available_anymore
