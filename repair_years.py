import database
from scraper import http_get, extract_json
from utils import normalize_year


def get_year_from_url(url):

    html = http_get(url)

    data = extract_json(html)

    if not data:
        return None


    candidates = []


    # nieuwe structuur
    try:
        candidates.append(
            data["props"]
            ["pageProps"]
            ["properData"]
            ["carDetails"]
            ["vehicle"]
            .get("firstRegistrationDate")
        )
    except:
        pass


    # oude structuur
    try:
        candidates.append(
            data["props"]
            ["pageProps"]
            ["listingDetails"]
            .get("firstRegistrationDate")
        )
    except:
        pass


    # algemene zoekactie
    def find_registration(obj):

        if isinstance(obj, dict):

            for k,v in obj.items():

                if k == "firstRegistrationDate":
                    return v

                result = find_registration(v)

                if result:
                    return result


        elif isinstance(obj,list):

            for item in obj:

                result = find_registration(item)

                if result:
                    return result


        return None


    candidates.append(
        find_registration(data)
    )


    for value in candidates:

        year = normalize_year(value)

        if year:
            return year


    return None

cars = database.get_all_cars()


fixed = 0


for car in cars:

    if car.year:
        continue


    print(
        "Checking:",
        car.id
    )


    year = get_year_from_url(
        car.url
    )


    if year:

        print(
            "FOUND:",
            year
        )


        database.update_car_year(
            car.id,
            year
        )


        fixed += 1


print()
print(
    "Fixed:",
    fixed
)
