#!/usr/bin/env python3

"""
AutoHunter v2.9-dev

Audi A5 Cabrio Search Engine

Main application
"""


import argparse
from datetime import datetime
import debug
import config
import database
import debug_car
import debug_score
import debug_options
import options
import descriptions
import scoring
import scraper
import pipeline
import pipeline_stats
import pipeline_report
import deals
import watchlist_report

version=f"{config.APP_NAME} {config.VERSION}"

def recheck_database():

    debug.info(
        "Database health check"
    )

    health = database.database_health()

    print()
    print("AutoHunter Database Check")
    print("-------------------------")
    print(
        f"Total cars:              {health['total']}"
    )
    print(
        f"With description:        {health['with_description']}"
    )
    print(
        f"Missing description:     {health['missing_description']}"
    )
    print(
        f"Options checked:        {health['options_checked']}"
    )
    print()


    debug.info(
        "Recalculating vehicle options"
    )

    import options

    cars = database.get_all_cars()

    updated = 0
    details_updated = 0

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
                details.get("interior_color", "")
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


    debug.info(
        f"Options updated: {updated}"
    )

    debug.info(
        f"Details updated: {details_updated}"
    )


    print(
        f"Options recalculated: {updated}"
    )

    print(
        f"Vehicle details updated: {details_updated}"
    )


def parse_arguments():

    parser = argparse.ArgumentParser(
        description="AutoHunter Audi A5 Cabrio"
    )

    parser.add_argument(
        "--options",
        action="store_true",
        help="Update vehicle options"
    )

    parser.add_argument(
        "--rescore",
        action="store_true",
        help="Recalculate scores"
    )

    parser.add_argument(
        "--recheck",
        action="store_true",
        help="Check database"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )

    parser.add_argument(
        "--debug-id",
        type=int,
        help="Debug specific car ID"
    )

    parser.add_argument(
        "--debug-options",
        action="store_true",
        help="Debug option detection"
    )

    parser.add_argument(
        "--debug-score",
        action="store_true",
        help="Explain score calculation"
    )

    parser.add_argument(
        "--descriptions",
        action="store_true",
        help="Update missing descriptions"
    )

    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Run complete processing pipeline"
    )

    parser.add_argument(
        "--ranking",
        action="store_true",
        help="Show top ranked cars"
    )


    parser.add_argument(
        "--recommendation",
        action="store_true",
        help="Show AI recommendation"
    )

    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate ranking report"
    )

    parser.add_argument(
        "--watchlist",
        action="store_true",
        help="Show personal watchlist"
    )

    parser.add_argument(
        "--today",
        action="store_true",
        help="Show new cars today"
    )

    parser.add_argument(
        "--debug-today",
        action="store_true",
        help="Debug today's interesting cars"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="Number of days for debug-today"
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"{config.APP_NAME} {config.VERSION}"
    )

    return parser.parse_args()


def run_pipeline():

    debug.info(
        "Starting AutoHunter pipeline"
    )

    run_id = pipeline.start_run()

    start_time = datetime.now()

    try:

        debug.info(
            "Scraping AutoScout24"
        )

        new_cars, not_available_anymore = scraper.run_scraper()

        debug.info(
            "Updating descriptions"
        )

        descriptions_updated = descriptions.update_missing_descriptions()

        debug.info(
            "Updating options"
        )

        options_updated = options.update_all_options()

        debug.info(
            "Recalculating scores"
        )

        scoring.recalculate_scores()

        debug.info(
            "Calculating deal scores"
        )

        deal_scores_updated = deals.update_deal_scores()

        debug.info(
            f"Deal scores updated: {deal_scores_updated}"
        )

        debug.info(
            "Checking deal alerts"
        )

        try:

            import telegram
            import database

            #
            # Deal alerts
            #

            top_deals = database.get_deals(5)

            for car in top_deals:

                if car.deal_score >= 40:

                    telegram.send_deal_alert(car)

            #
            # Nieuwe watchlist matches
            #

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

                    debug.info(
                        f"Marked as sent: {car.id}"
                    )

        except Exception as e:

            debug.info(
                f"Deal/watchlist alert failed: {e}"
            )

        debug.info(
            "Collecting pipeline statistics"
        )

        stats = pipeline_stats.get_pipeline_stats()

        run_stats = {
            "status": "SUCCESS",
            "duration_seconds": 0,
            "new_cars": new_cars,
            "not_available_anymore": not_available_anymore,
            "price_drops": stats["price_drops"],
            "high_score_cars": stats["high_score_cars"],
            "descriptions_updated": descriptions_updated,
            "options_updated": options_updated,
            "alerts_sent": 0,
        }

        try:

            import telegram

            telegram.send_pipeline_summary(
                run_stats=run_stats,
                db_stats=stats
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

        except Exception as e:

            debug.info(
                f"Telegram notification failed: {e}"
            )

        debug.info(
            f"High score cars: {stats['high_score_cars']}"
        )

        debug.info(
            f"Price drops: {stats['price_drops']}"
        )

        debug.info(
            "Cleaning old pipeline runs"
        )

        deleted_runs = pipeline.cleanup_runs(
            90
        )

        debug.info(
            f"Deleted old pipeline runs: {deleted_runs}"
        )


        debug.info(
            "Pipeline completed"
        )


        duration = int(
            (datetime.now() - start_time).total_seconds()
        )


        pipeline.finish_run(
            run_id,
            status="SUCCESS",
            new_cars=new_cars,
            not_available_anymore=not_available_anymore,
            descriptions_updated=descriptions_updated,
            options_updated=options_updated,
            deal_scores_updated=deal_scores_updated,
            high_score_cars=stats["high_score_cars"],
            price_drops=stats["price_drops"],
            duration_seconds=duration
        )

        pipeline_report.print_summary(
            run_id
        )

    except Exception as e:

        pipeline.finish_run(
            run_id,
            status="FAILED",
            error_message=str(e)
        )

        debug.info(
            f"Pipeline failed: {e}"
        )

        raise


def is_interesting_car(car):

    if car.watchlist_match != 1:
        return False

    return (
        car.personal_score >= 70
        or car.deal_score >= 40
    )



def debug_today(days=0):

    if days > 0:

        cars = database.get_recent_cars(
            days,
            10
        )

    else:

        cars = database.get_todays_cars(10)

    print()
    print("================================")
    print(" AUTOHUNTER DEBUG TODAY")
    print("================================")
    print()

    print(f"Nieuwe auto's: {len(cars)}")
    print()

    for car in cars:

        match = is_interesting_car(car)

        print(car.title)
        print("----------------")
        print(f"Final score:    {car.final_score}")
        print(f"Personal score: {car.personal_score}")
        print(f"Deal score:     {car.deal_score}")

        if match:
            print("Resultaat:      MATCH")
        else:
            print("Resultaat:      GEEN MATCH")

        print()


def main():

    args = parse_arguments()

    if args.debug:
        debug.enable_debug()

        debug.info(
            "Debug mode enabled"
        )

    debug.info(
        f"{config.APP_NAME} {config.VERSION} gestart"
    )

    debug.info(
        f"Starttijd: {datetime.now()}"
    )

    if args.debug_id:

        debug.info(
            f"Debug car ID: {args.debug_id}"
        )

        car = database.get_car(
            args.debug_id
        )

        if car:

            if args.debug:

                debug_car.show_car(car)

                debug_score.explain_score(car)

                debug_options.explain_options(car)

            else:

                if args.debug_score:

                    debug_score.explain_score(car)

                if args.debug_options:

                    debug_options.explain_options(car)

    elif args.options:
        debug.info(
            "Option update mode"
        )

        import options
        options.update_all_options()

    elif args.descriptions:

        debug.info(
            "Description update mode"
        )

        descriptions.update_missing_descriptions()

    elif args.rescore:
        debug.info(
            "Rescore mode"
        )

        scoring.recalculate_scores()

    elif args.recheck:
        recheck_database()


    elif args.debug_options:
        debug.info(
            "Option debug mode"
        )

    elif args.pipeline:

        debug.info(
            "Pipeline mode"
        )

        run_pipeline()

    elif args.ranking:

        import reporting

        reporting.show_ranking()


    elif args.recommendation:

        import recommendation_report

        recommendation_report.show_recommendation()


    elif args.report:

        import reporting

        reporting.generate_report()

    elif args.watchlist:

        debug.info(
            "Watchlist report"
        )

        watchlist_report.show_watchlist()

    elif args.today:

        import reporting

        reporting.show_today()

    elif args.debug_today:

        debug_today(
            args.days
        )

    else:

        debug.info(
            "No action specified"
        )

if __name__ == "__main__":
    main()
