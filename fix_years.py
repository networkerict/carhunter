#!/usr/bin/env python3

import sqlite3
import re

from config import DATABASE

DB = DATABASE

def extract_year(text):

    if not text:
        return None

    patterns = [

        # fingerprint oud formaat
        r"\b\d{2}[-/.](20\d{2})\b",

        # Erstzulassung
        r"Erstzulassung[^0-9]*(20\d{2})",

        # EZ
        r"\bEZ[^0-9]*(20\d{2})",

        # Baujahr
        r"Baujahr[^0-9]*(20\d{2})",

        # algemeen
        r"\b(20[1-2][0-9])\b",
    ]

    for p in patterns:

        m = re.search(
            p,
            text,
            re.IGNORECASE
        )

        if m:

            year=int(m.group(1))

            if 2008 <= year <= 2026:
                return str(year)

    return None



conn=sqlite3.connect(DB)
cur=conn.cursor()


cur.execute("""
SELECT id,fingerprint,description,url
FROM cars
WHERE year IS NULL OR year=''
""")


cars=cur.fetchall()

updated=0


for car_id,fingerprint,description,url in cars:

    source=" ".join(
        x for x in [
            fingerprint,
            description,
            url
        ]
        if x
    )


    year=extract_year(source)


    if year:

        cur.execute(
        """
        UPDATE cars
        SET year=?
        WHERE id=?
        """,
        (
            year,
            car_id
        ))

        updated+=1


conn.commit()


print("Updated:",updated)


cur.execute("""
SELECT COUNT(*)
FROM cars
WHERE year IS NULL OR year=''
""")


print(
"Remaining empty years:",
cur.fetchone()[0]
)


conn.close()
