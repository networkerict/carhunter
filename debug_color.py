import scraper
import json


url="https://www.autoscout24.de/angebote/audi-a5-40-tfsi-s-line-navi-plus-led-kamera-benzin-blau-cat_ma9mo19047-998105b4-18f6-409e-99f9-ed948a663701"


html = scraper.http_get(url)

data = scraper.extract_json(html)

cd = scraper.get_listing_details(data)


with open("/tmp/audi_color.json","w") as f:
    json.dump(
        cd,
        f,
        indent=2,
        ensure_ascii=False
    )

print("klaar")
