"""
AutoHunter v2.9
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
            started_at,
            finished_at,
            status,
            new_cars,
            not_available_anymore,
            descriptions_updated,
            options_updated,
            high_score_cars,
            price_drops,
            alerts_sent,
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
    print(f"Status:              {run[3]}")
    print(f"Started:             {run[1]}")
    print(f"Finished:            {run[2]}")
    print(f"Duration:            {run[11]} sec")
    print()

    print(f"New cars:            {run[4]}")
    print(f"Not available:       {run[5]}")
    print(f"Descriptions:        {run[6]}")
    print(f"Options checked:     {run[7]}")
    print(f"Alerts sent:         {run[10]}")
    print()

    print(f"High score cars:     {run[8]}")
    print(f"Price drops:         {run[9]}")

    print()
    print("================================")
    print()
