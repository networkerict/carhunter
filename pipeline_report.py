"""
AutoHunter v2.9-dev
Pipeline summary report
"""

import database


def print_summary(run_id):

    conn = database.get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            status,
            new_cars,
            descriptions_updated,
            options_updated,
            high_score_cars,
            price_drops,
            duration_seconds
        FROM pipeline_runs
        WHERE id = ?
        """,
        (run_id,)
    )

    run = cursor.fetchone()

    conn.close()

    if not run:
        return


    print()
    print("================================")
    print(" AUTOHUNTER PIPELINE SUMMARY")
    print("================================")
    print()

    print(f"Run:                 #{run[0]}")
    print(f"Status:              {run[1]}")
    print(f"Duration:            {run[7]} sec")
    print()

    print(f"New cars:            {run[2]}")
    print(f"Descriptions:        {run[3]}")
    print(f"Options checked:     {run[4]}")
    print()

    print(f"High score cars:     {run[5]}")
    print(f"Price drops:         {run[6]}")

    print()
    print("================================")
    print()
