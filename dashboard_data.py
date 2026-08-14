"""
AutoHunter v3.0-dev
Dashboard data layer
"""

import database
import pipeline_stats
import recommendation


def is_interesting(car):

    if car.watchlist_match != 1:
        return False

    return (
        car.personal_score >= 70
        or car.deal_score >= 40
    )


def get_dashboard_data():

    today = database.get_todays_cars(10)

    recent = database.get_recent_cars(
        7,
        10
    )

    interesting = [
        car
        for car in recent
        if is_interesting(car)
    ]

    ranking = database.get_ranked_cars(10)

    deals = database.get_deals(10)

    stats = pipeline_stats.get_pipeline_stats()
    inventory = database.get_inventory_counts()
    source_counts = database.get_source_counts()

    latest_run = pipeline_stats.get_latest_run()

    recent_runs = pipeline_stats.get_recent_runs()

    recommendations = {}

    for car in interesting:

        recommendations[car.id] = recommendation.explain_car(
            car
        )


    return {
        "today": today,
        "interesting": interesting,
        "ranking": ranking,
        "deals": deals,
        "stats": stats,
        "inventory": inventory,
        "source_counts": source_counts,
        "latest_run": latest_run,
        "recent_runs": recent_runs,
        "recommendations": recommendations
    }
