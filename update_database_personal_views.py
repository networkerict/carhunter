from pathlib import Path

file = Path("database.py")

text = file.read_text()


replacements = {

"""        ORDER BY
            personal_score DESC,
            final_score DESC
        LIMIT ?
        """,
"""        ORDER BY
            personal_score DESC,
            final_score DESC
        LIMIT ?
        """,

}


# get_ranked_cars en get_ranking controleren we gericht
old1 = """        ORDER BY
            final_score DESC
        LIMIT ?
        """


new1 = """        ORDER BY
            personal_score DESC,
            final_score DESC
        LIMIT ?
        """


count = text.count(old1)

if count:
    text = text.replace(old1, new1)

    print(
        f"Aangepast: {count} ranking queries"
    )
else:
    print(
        "Geen pure final_score ranking queries gevonden"
    )


# deals moeten persoonlijk worden
old2 = """        SELECT *
        FROM cars
        WHERE deal_score > 0
        ORDER BY
            personal_score DESC,
            deal_score DESC,
            final_score DESC
        LIMIT ?
"""


new2 = """        SELECT *
        FROM cars
        WHERE deal_score > 0
        AND watchlist_match = 1
        ORDER BY
            personal_score DESC,
            deal_score DESC,
            final_score DESC
        LIMIT ?
"""


if old2 in text:

    text = text.replace(
        old2,
        new2
    )

    print(
        "Deals beperkt tot watchlist matches"
    )

else:

    print(
        "Deal query niet aangepast"
    )


file.write_text(text)

