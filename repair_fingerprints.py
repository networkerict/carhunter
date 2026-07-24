#!/usr/bin/env python3

import sqlite3

from config import DATABASE

DB = DATABASE

def create_fingerprint(title, km, year):

    parts = title.split()

    make = parts[0] if len(parts) > 0 else ""
    model = parts[1] if len(parts) > 1 else ""

    return "|".join(
        [
            make,
            model,
            "",
            str(km or ""),
            str(year or "")
        ]
    )


con = sqlite3.connect(DB)

cur = con.cursor()


rows = cur.execute(
    """
    SELECT id,title,km,year
    FROM cars
    WHERE fingerprint IS NULL
    """
).fetchall()


print(f"Found {len(rows)} cars")


fixed = 0


for row in rows:

    car_id, title, km, year = row

    fingerprint = create_fingerprint(
        title,
        km,
        year
    )

    # voorkomen van duplicate fingerprints
    original = fingerprint

    counter = 1

    while cur.execute(
        """
        SELECT 1
        FROM cars
        WHERE fingerprint = ?
        """,
        (fingerprint,)
    ).fetchone():

        fingerprint = (
            original
            + "|"
            + str(car_id)
        )

        break

    print(
        f"{car_id}: {fingerprint}"
    )

    cur.execute(
        """
        UPDATE cars
        SET fingerprint = ?
        WHERE id = ?
        """,
        (
            fingerprint,
            car_id
        )
    )

    fixed += 1


con.commit()
con.close()


print()
print(f"Fixed: {fixed}")

