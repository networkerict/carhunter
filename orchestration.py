#!/usr/bin/env python3

"""
AutoHunter v2.9-dev
Canonical orchestration pipeline
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import database
import debug
import pipeline
import pipeline_report
import pipeline_stats


@dataclass(frozen=True)
class StageDefinition:
    name: str
    description: str
    runner: Callable[["PipelineContext"], None]


@dataclass(frozen=True)
class ModeDefinition:
    name: str
    stages: List[str]
    force_options_refresh: bool = False
    track_pipeline_run: bool = False
    print_summary: bool = False


@dataclass
class PipelineContext:
    mode: str
    dry_run: bool = False
    started_at: datetime = field(default_factory=datetime.now)
    run_id: Optional[int] = None
    stage_results: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)
    alerts_sent: int = 0


PIPELINE_STAGES: Dict[str, StageDefinition] = {}


def register_stage(name: str, description: str):

    def decorator(func: Callable[[PipelineContext], None]):
        PIPELINE_STAGES[name] = StageDefinition(
            name=name,
            description=description,
            runner=func,
        )
        return func

    return decorator


PIPELINE_MODES: Dict[str, ModeDefinition] = {
    "full": ModeDefinition(
        name="full",
        stages=[
            "scrape",
            "descriptions",
            "options",
            "scores",
            "deal_scores",
            "notifications",
            "statistics",
            "summary_notifications",
            "cleanup",
        ],
        track_pipeline_run=True,
        print_summary=True,
    ),
    "rescore": ModeDefinition(
        name="rescore",
        stages=[
            "options",
            "scores",
            "deal_scores",
        ],
        force_options_refresh=True,
    ),
    "options": ModeDefinition(
        name="options",
        stages=[
            "options",
        ],
    ),
    "descriptions": ModeDefinition(
        name="descriptions",
        stages=[
            "descriptions",
        ],
    ),
    "repair": ModeDefinition(
        name="repair",
        stages=[
            "repair",
        ],
    ),
    "recheck": ModeDefinition(
        name="recheck",
        stages=[
            "recheck",
        ],
    ),
}


def is_interesting_car(car):

    if car.watchlist_match != 1:
        return False

    return (
        car.personal_score >= 70
        or car.deal_score >= 40
    )


def run_pipeline(mode="full", dry_run=False):

    if mode not in PIPELINE_MODES:
        raise ValueError(
            f"Unknown pipeline mode: {mode}"
        )

    mode_definition = PIPELINE_MODES[mode]

    context = PipelineContext(
        mode=mode,
        dry_run=dry_run,
    )

    debug.info(
        f"Starting canonical pipeline: {mode}"
    )

    if mode_definition.track_pipeline_run:
        context.run_id = pipeline.start_run()

    try:

        for stage_name in mode_definition.stages:

            stage = PIPELINE_STAGES[stage_name]

            debug.info(
                f"Pipeline stage: {stage.name}"
            )

            stage.runner(context)

        if mode_definition.track_pipeline_run:
            _finish_pipeline_run(
                context,
                status="SUCCESS",
            )

        if mode_definition.print_summary and context.run_id is not None:
            pipeline_report.print_summary(
                context.run_id
            )

        debug.info(
            f"Canonical pipeline completed: {mode}"
        )

        return context

    except Exception as exc:

        if mode_definition.track_pipeline_run and context.run_id is not None:
            _finish_pipeline_run(
                context,
                status="FAILED",
                error_message=str(exc),
            )

        debug.info(
            f"Canonical pipeline failed ({mode}): {exc}"
        )

        raise


def _finish_pipeline_run(
    context,
    status,
    error_message=None,
):

    duration = int(
        (datetime.now() - context.started_at).total_seconds()
    )

    pipeline.finish_run(
        context.run_id,
        status=status,
        new_cars=context.stage_results.get("new_cars", 0),
        not_available_anymore=context.stage_results.get("not_available_anymore", 0),
        descriptions_updated=context.stage_results.get("descriptions_updated", 0),
        options_updated=context.stage_results.get("options_updated", 0),
        deal_scores_updated=context.stage_results.get("deal_scores_updated", 0),
        high_score_cars=context.stage_results.get("high_score_cars", 0),
        price_drops=context.stage_results.get("price_drops", 0),
        alerts_sent=context.alerts_sent,
        duration_seconds=duration,
        error_message=error_message,
    )


@register_stage(
    "scrape",
    "Scrape AutoScout24 and update the inventory.",
)
def stage_scrape(context):

    import scraper

    debug.info(
        "Scraping AutoScout24"
    )

    new_cars, not_available_anymore = scraper.run_scraper()

    context.stage_results["new_cars"] = new_cars
    context.stage_results["not_available_anymore"] = not_available_anymore


@register_stage(
    "descriptions",
    "Backfill missing vehicle descriptions.",
)
def stage_descriptions(context):

    import descriptions

    debug.info(
        "Updating descriptions"
    )

    context.stage_results["descriptions_updated"] = (
        descriptions.update_missing_descriptions()
    )


@register_stage(
    "options",
    "Refresh detected options and option scores.",
)
def stage_options(context):

    import options

    debug.info(
        "Updating options"
    )

    force_refresh = PIPELINE_MODES[
        context.mode
    ].force_options_refresh

    context.stage_results["options_updated"] = (
        options.update_all_options(
            force=force_refresh
        )
    )


@register_stage(
    "scores",
    "Recalculate car, value, premium, final, personal, and watchlist scores.",
)
def stage_scores(context):

    import scoring

    debug.info(
        "Recalculating scores"
    )

    scoring.recalculate_scores()


@register_stage(
    "deal_scores",
    "Recalculate deal scores.",
)
def stage_deal_scores(context):

    import deals

    debug.info(
        "Calculating deal scores"
    )

    context.stage_results["deal_scores_updated"] = (
        deals.update_deal_scores()
    )


@register_stage(
    "notifications",
    "Send deal and watchlist alerts.",
)
def stage_notifications(context):

    debug.info(
        "Checking deal alerts"
    )

    try:

        import telegram

        top_deals = database.get_deals(5)

        for car in top_deals:

            if car.deal_score >= 40 and telegram.send_deal_alert(car):
                context.alerts_sent += 1

        watchlist_cars = database.get_unsent_watchlist_matches()

        debug.info(
            f"New watchlist matches: {len(watchlist_cars)}"
        )

        for car in watchlist_cars:

            debug.info(
                f"Sending watchlist alert: {car.id} - {car.title}"
            )

            result = telegram.send_watchlist_alert(car)

            debug.info(
                f"Telegram result: {result}"
            )

            if result:

                database.mark_watchlist_sent(car.id)
                context.alerts_sent += 1

                debug.info(
                    f"Marked as sent: {car.id}"
                )

    except Exception as exc:

        debug.info(
            f"Deal/watchlist alert failed: {exc}"
        )


@register_stage(
    "statistics",
    "Collect pipeline statistics.",
)
def stage_statistics(context):

    debug.info(
        "Collecting pipeline statistics"
    )

    context.stats = pipeline_stats.get_pipeline_stats()
    context.stage_results["high_score_cars"] = context.stats["high_score_cars"]
    context.stage_results["price_drops"] = context.stats["price_drops"]


@register_stage(
    "summary_notifications",
    "Send pipeline summary and today report notifications.",
)
def stage_summary_notifications(context):

    try:

        import telegram

        run_stats = {
            "status": "SUCCESS",
            "duration_seconds": int(
                (datetime.now() - context.started_at).total_seconds()
            ),
            "new_cars": context.stage_results.get("new_cars", 0),
            "not_available_anymore": context.stage_results.get("not_available_anymore", 0),
            "price_drops": context.stage_results.get("price_drops", 0),
            "high_score_cars": context.stage_results.get("high_score_cars", 0),
            "descriptions_updated": context.stage_results.get("descriptions_updated", 0),
            "options_updated": context.stage_results.get("options_updated", 0),
            "alerts_sent": context.alerts_sent,
        }

        telegram.send_pipeline_summary(
            run_stats=run_stats,
            db_stats=context.stats,
        )

        today_cars = database.get_todays_cars(10)

        interesting_cars = [
            car
            for car in today_cars
            if is_interesting_car(car)
        ]

        if interesting_cars:
            telegram.send_today_report(
                interesting_cars
            )

    except Exception as exc:

        debug.info(
            f"Telegram notification failed: {exc}"
        )


@register_stage(
    "cleanup",
    "Clean historical pipeline runs.",
)
def stage_cleanup(context):

    debug.info(
        "Cleaning old pipeline runs"
    )

    context.stage_results["deleted_runs"] = (
        pipeline.cleanup_runs(90)
    )

    debug.info(
        f"Deleted old pipeline runs: {context.stage_results['deleted_runs']}"
    )


@register_stage(
    "repair",
    "Repair incomplete vehicles by re-fetching source data.",
)
def stage_repair(context):

    import repair_engine

    debug.info(
        "Running repair engine"
    )

    context.stage_results["repair_report"] = (
        repair_engine.run_repair(
            dry_run=context.dry_run
        )
    )


@register_stage(
    "recheck",
    "Refresh vehicle details and missing option analysis for diagnostics.",
)
def stage_recheck(context):

    import options
    import scraper

    debug.info(
        "Database health check"
    )

    health = database.database_health()
    cars = database.get_all_cars()
    updated = 0
    details_updated = 0

    debug.info(
        "Recalculating vehicle options"
    )

    for car in cars:

        if not car.url:
            continue

        details = scraper.fetch_car_details(
            car.url
        )

        if details:

            database.update_car_details(
                car.id,
                details.get("color", ""),
                details.get("color_detail", ""),
                details.get("interior_color", ""),
                details.get("upholstery", ""),
                details.get("gearbox", ""),
                details.get("body_type", ""),
                details.get("hp", 0),
                details.get("drive", "")
            )

            details_updated += 1

            if car.options_score == 0:

                debug.info(
                    f"Analyzing options: {car.url}"
                )

                found, score = options.analyze_options(
                    details
                )

                if found:

                    database.update_car_options(
                        car.id,
                        ", ".join(found),
                        score
                    )

                    updated += 1

    context.stage_results["recheck_report"] = {
        "health": health,
        "options_updated": updated,
        "details_updated": details_updated,
    }