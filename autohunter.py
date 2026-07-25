#!/usr/bin/env python3

"""
AutoHunter v2.9

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
import orchestration
import repair_engine
import watchlist_report

version=f"{config.APP_NAME} {config.VERSION}"

def recheck_database():

    context = orchestration.run_pipeline(
        "recheck"
    )

    report = context.stage_results[
        "recheck_report"
    ]

    health = report["health"]

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
    print(
        f"Options recalculated: {report['options_updated']}"
    )

    print(
        f"Vehicle details updated: {report['details_updated']}"
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
        "--repair",
        action="store_true",
        help="Repair incomplete cars by re-fetching source data"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview repairs without writing changes"
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
    return orchestration.run_pipeline(
        "full"
    )


def is_interesting_car(car):
    return orchestration.is_interesting_car(
        car
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

        orchestration.run_pipeline(
            "options"
        )

    elif args.descriptions:

        debug.info(
            "Description update mode"
        )

        orchestration.run_pipeline(
            "descriptions"
        )

    elif args.rescore:
        debug.info(
            "Rescore mode"
        )

        orchestration.run_pipeline(
            "rescore"
        )

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

    elif args.repair:

        debug.info("Repair mode")

        context = orchestration.run_pipeline(
            "repair",
            dry_run=args.dry_run,
        )
        report = context.stage_results[
            "repair_report"
        ]
        repair_engine.engine.print_report(report)

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
