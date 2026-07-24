"""
AutoHunter v2.9-dev
Pipeline tracking
"""

from datetime import datetime
import database


def start_run():

    conn = database.get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO pipeline_runs
        (
            started_at,
            status
        )
        VALUES (?, ?)
        """,
        (
            datetime.now(),
            "RUNNING"
        )
    )

    run_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return run_id


def finish_run(
    run_id,
    status="SUCCESS",
    new_cars=0,
    not_available_anymore=0,
    descriptions_updated=0,
    options_updated=0,
    deal_scores_updated=0,
    high_score_cars=0,
    price_drops=0,
    alerts_sent=0,
    duration_seconds=0,
    error_message=None
):


    conn = None

    try:

        conn = database.get_connection()

        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE pipeline_runs
            SET
                finished_at = ?,
                status = ?,
                new_cars = ?,
                not_available_anymore = ?,
                descriptions_updated = ?,
                options_updated = ?,
                deal_scores_updated = ?,
                high_score_cars = ?,
                price_drops = ?,
                alerts_sent = ?,
                duration_seconds = ?,
                error_message = ?
            WHERE id = ?
            """,
            (
                datetime.now(),
                status,
                new_cars,
                not_available_anymore,
                descriptions_updated,
                options_updated,
                deal_scores_updated,
                high_score_cars,
                price_drops,
                alerts_sent,
                duration_seconds,
                error_message,
                run_id
            )
        )

        conn.commit()


    finally:

        if conn:
            conn.close()



def cleanup_runs(days=90):

    conn = database.get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM pipeline_runs
        WHERE started_at < datetime('now', ?)
        """,
        (
            f"-{days} days",
        )
    )

    deleted = cursor.rowcount

    conn.commit()
    conn.close()

    return deleted
