"""
AutoHunter v2.6-dev
Pipeline statistics
"""

import database
from datetime import datetime


def _format_datetime(value):

    if not value:
        return "—"

    try:
        return datetime.fromisoformat(value).strftime("%d-%m-%Y %H:%M")
    except (TypeError, ValueError):
        return str(value)


def get_run(run_id):

    conn = database.get_connection()

    row = conn.execute(
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
            deal_scores_updated,
            high_score_cars,
            price_drops,
            alerts_sent,
            duration_seconds,
            error_message
        FROM pipeline_runs
        WHERE id = ?
        """,
        (run_id,)
    ).fetchone()

    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "started_at": _format_datetime(row[1]),
        "finished_at": _format_datetime(row[2]),
        "status": row[3] or "UNKNOWN",
        "new_cars": row[4] or 0,
        "not_available_anymore": row[5] or 0,
        "descriptions_updated": row[6] or 0,
        "options_updated": row[7] or 0,
        "deal_scores_updated": row[8] or 0,
        "high_score_cars": row[9] or 0,
        "price_drops": row[10] or 0,
        "alerts_sent": row[11] or 0,
        "duration_seconds": row[12] or 0,
        "error_message": row[13],
    }


def get_latest_run():
    conn = database.get_connection()

    row = conn.execute(
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
            deal_scores_updated,
            high_score_cars,
            price_drops,
            alerts_sent,
            duration_seconds,
            error_message
        FROM pipeline_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "started_at": _format_datetime(row[1]),
        "finished_at": _format_datetime(row[2]),
        "status": row[3] or "UNKNOWN",
        "new_cars": row[4] or 0,
        "not_available_anymore": row[5] or 0,
        "descriptions_updated": row[6] or 0,
        "options_updated": row[7] or 0,
        "deal_scores_updated": row[8] or 0,
        "high_score_cars": row[9] or 0,
        "price_drops": row[10] or 0,
        "alerts_sent": row[11] or 0,
        "duration_seconds": row[12] or 0,
        "error_message": row[13],
    }





def get_recent_runs(limit=10):

    conn = database.get_connection()

    rows = conn.execute(
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
            deal_scores_updated,
            high_score_cars,
            price_drops,
            alerts_sent,
            duration_seconds,
            error_message
        FROM pipeline_runs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    conn.close()

    return [
        {
            "id": row[0],
            "started_at": _format_datetime(row[1]),
            "finished_at": _format_datetime(row[2]),
            "status": row[3] or "UNKNOWN",
            "new_cars": row[4] or 0,
            "not_available_anymore": row[5] or 0,
            "descriptions_updated": row[6] or 0,
            "options_updated": row[7] or 0,
            "deal_scores_updated": row[8] or 0,
            "high_score_cars": row[9] or 0,
            "price_drops": row[10] or 0,
            "alerts_sent": row[11] or 0,
            "duration_seconds": row[12] or 0,
            "error_message": row[13],
        }
        for row in rows
    ]


def get_pipeline_stats():

    cars = database.get_all_cars()
    inventory = database.get_inventory_counts()

    high_score = 0
    price_drops = 0

    for car in cars:

        if car.final_score >= 80:
            high_score += 1

        if car.price_drop and car.price_drop > 0:
            price_drops += 1

    return {
        "high_score_cars": high_score,
        "price_drops": price_drops,
        "active_cars": inventory["active"],
        "new_cars": inventory["new"],
        "sold_cars": inventory["sold"],
        "not_available_anymore_total": inventory["sold"],
    }

