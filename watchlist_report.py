"""
AutoHunter v2.9
Personal Watchlist Report
"""

import database


def show_watchlist():

    conn = database.get_connection()

    rows = conn.execute(
        """
        SELECT
            id,
            title,
            price,
            year,
            km,
            personal_score
        FROM cars
        WHERE watchlist_match = 1
        ORDER BY personal_score DESC;
        """
    ).fetchall()

    conn.close()

    print()
    print("========================================")
    print("        PERSONAL WATCHLIST")
    print("========================================")
    print()

    if not rows:
        print("No matching cars found.")
        return

    for index, row in enumerate(rows, start=1):

        car_id, title, price, year, km, personal_score = row

        print(f"#{index}")
        print(title)
        print(f"€{price:,}".replace(",", "."))
        print(f"{year} | {km:,} km".replace(",", "."))
        print(f"Personal Score : {personal_score}")
        print("----------------------------------------")
