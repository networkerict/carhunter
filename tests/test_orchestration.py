import unittest
from argparse import Namespace
from unittest import mock

import autohunter
import orchestration
import webapp


class OrchestrationTests(unittest.TestCase):

    def test_rescore_mode_uses_canonical_stage_order(self):
        calls = []

        with mock.patch(
            "options.update_all_options",
            side_effect=lambda force=False: calls.append(("options", force)) or 11,
        ), mock.patch(
            "scoring.recalculate_scores",
            side_effect=lambda: calls.append(("scores", None)),
        ), mock.patch(
            "deals.update_deal_scores",
            side_effect=lambda: calls.append(("deal_scores", None)) or 22,
        ):
            context = orchestration.run_pipeline(
                "rescore"
            )

        self.assertEqual(
            calls,
            [
                ("options", True),
                ("scores", None),
                ("deal_scores", None),
            ],
        )
        self.assertEqual(
            context.stage_results["options_updated"],
            11,
        )
        self.assertEqual(
            context.stage_results["deal_scores_updated"],
            22,
        )

    def test_full_mode_uses_canonical_stage_order_and_tracking(self):
        calls = []
        compatibility_result = mock.Mock(new_cars=2, not_available_anymore=1)
        should_fetch_detail = mock.Mock()
        
        # Mock the multi-source coordinator result
        multi_source_result = mock.Mock(
            all_snapshots=[mock.sentinel.snapshot],
            active_fingerprints=["fp-1"],
            overall_outcome="SUCCESS",
            total_snapshots=1,
            total_accepted=1,
            total_rejected=0,
            per_instance_results=[],  # Empty list for this test
        )

        with mock.patch(
            "pipeline.start_run",
            side_effect=lambda: calls.append("start_run") or 42,
        ), mock.patch(
            "sources.build_default_source_registry",
        ) as build_registry, mock.patch(
            "sources.build_source_instances",
        ) as build_instances, mock.patch(
            "sources.build_source_coordinator",
        ) as build_coordinator, mock.patch(
            "source_compatibility.apply_compatibility_inventory_updates",
            side_effect=lambda snapshots, active_fingerprints, dry_run=False: calls.append("persist") or compatibility_result,
        ), mock.patch(
            "source_compatibility.should_fetch_detail_for_listing",
            should_fetch_detail,
        ), mock.patch(
            "descriptions.update_missing_descriptions",
            side_effect=lambda: calls.append("descriptions") or 3,
        ), mock.patch(
            "options.update_all_options",
            side_effect=lambda force=False: calls.append(("options", force)) or 4,
        ), mock.patch(
            "scoring.recalculate_scores",
            side_effect=lambda: calls.append("scores"),
        ), mock.patch(
            "deals.update_deal_scores",
            side_effect=lambda: calls.append("deal_scores") or 5,
        ), mock.patch(
            "database.get_deals",
            side_effect=lambda limit=20: calls.append(("get_deals", limit)) or [],
        ), mock.patch(
            "database.get_unsent_watchlist_matches",
            side_effect=lambda: calls.append("get_unsent_watchlist_matches") or [],
        ), mock.patch(
            "pipeline_stats.get_pipeline_stats",
            side_effect=lambda: calls.append("statistics") or {
                "high_score_cars": 6,
                "price_drops": 7,
                "active_cars": 8,
                "new_cars": 2,
                "sold_cars": 1,
                "not_available_anymore_total": 1,
            },
        ), mock.patch(
            "telegram.send_pipeline_summary",
            side_effect=lambda run_stats=None, db_stats=None: calls.append("send_pipeline_summary") or True,
        ), mock.patch(
            "database.get_todays_cars",
            side_effect=lambda limit=10: calls.append(("get_todays_cars", limit)) or [],
        ), mock.patch(
            "pipeline.cleanup_runs",
            side_effect=lambda days=90: calls.append(("cleanup_runs", days)) or 9,
        ), mock.patch(
            "pipeline.finish_run",
            side_effect=lambda *args, **kwargs: calls.append(("finish_run", kwargs.get("status", args[1] if len(args) > 1 else None))),
        ), mock.patch(
            "pipeline_report.print_summary",
            side_effect=lambda run_id: calls.append(("print_summary", run_id)),
        ):
            build_instances.return_value = []
            coordinator_mock = mock.Mock()
            coordinator_mock.execute_sources.side_effect = lambda instances, run_id=None, dry_run=False, should_fetch_detail=None: calls.append("scrape") or multi_source_result
            build_coordinator.return_value = coordinator_mock
            context = orchestration.run_pipeline(
                "full"
            )

        self.assertEqual(
            calls,
            [
                "start_run",
                "scrape",
                "persist",
                "descriptions",
                ("options", False),
                "scores",
                "deal_scores",
                ("get_deals", 5),
                "get_unsent_watchlist_matches",
                "statistics",
                "send_pipeline_summary",
                ("get_todays_cars", 10),
                ("cleanup_runs", 90),
                ("finish_run", "SUCCESS"),
                ("print_summary", 42),
            ],
        )
        self.assertEqual(context.run_id, 42)
        self.assertEqual(context.stage_results["new_cars"], 2)
        self.assertEqual(context.stage_results["deal_scores_updated"], 5)
        self.assertEqual(context.stage_results["high_score_cars"], 6)

    def test_cli_processing_modes_delegate_to_canonical_pipeline(self):
        cases = [
            ("options", {"options": True}, mock.call("options")),
            ("descriptions", {"descriptions": True}, mock.call("descriptions")),
            ("rescore", {"rescore": True}, mock.call("rescore")),
            ("pipeline", {"pipeline": True}, mock.call("full")),
            ("recheck", {"recheck": True}, mock.call("recheck")),
            ("repair", {"repair": True, "dry_run": True}, mock.call("repair", dry_run=True)),
        ]

        defaults = {
            "options": False,
            "rescore": False,
            "recheck": False,
            "debug": False,
            "debug_id": None,
            "debug_options": False,
            "debug_score": False,
            "descriptions": False,
            "pipeline": False,
            "ranking": False,
            "recommendation": False,
            "report": False,
            "watchlist": False,
            "today": False,
            "repair": False,
            "dry_run": False,
            "debug_today": False,
            "days": 0,
        }

        for label, overrides, expected_call in cases:
            with self.subTest(label=label):
                args = defaults.copy()
                args.update(overrides)
                namespace = Namespace(**args)

                with mock.patch(
                    "autohunter.parse_arguments",
                    return_value=namespace,
                ), mock.patch(
                    "orchestration.run_pipeline",
                    return_value=mock.Mock(stage_results={
                        "repair_report": {},
                        "recheck_report": {
                            "health": {
                                "total": 0,
                                "with_description": 0,
                                "missing_description": 0,
                                "options_checked": 0
                            },
                            "options_updated": 0,
                            "details_updated": 0,
                        }
                    }),
                ) as run_pipeline, mock.patch(
                    "repair_engine.engine.print_report",
                ):
                    autohunter.main()

                run_pipeline.assert_called_once_with(*expected_call.args, **expected_call.kwargs)

    def test_web_rescore_delegates_to_canonical_pipeline(self):
        client = webapp.app.test_client()

        with mock.patch(
            "orchestration.run_pipeline"
        ) as run_pipeline:
            response = client.get(
                "/rescore"
            )

        self.assertEqual(
            response.status_code,
            302,
        )
        run_pipeline.assert_called_once_with(
            "rescore"
        )