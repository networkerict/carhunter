#!/usr/bin/env python3

"""
AutoHunter v3.0
Enterprise Data Repair Engine
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import config
import database
import debug
import scraper
from models import Car


FIELD_CONFIDENCE = {
    "price": "HIGH",
    "description": "MEDIUM",
    "options_found": "HIGH",
    "body_type": "MEDIUM",
    "hp": "HIGH",
    "drive": "HIGH",
    "gearbox": "HIGH",
    "upholstery": "MEDIUM",
    "interior_color": "MEDIUM",
    "color": "MEDIUM",
    "color_detail": "MEDIUM",
    "km": "MEDIUM",
    "year": "MEDIUM",
}


class RepairEngine:
    def __init__(self) -> None:
        self.report = {
            "cars_checked": 0,
            "cars_analyzed": 0,
            "cars_repaired": 0,
            "cars_unchanged": 0,
            "cars_skipped": 0,
            "cars_unavailable": 0,
            "fields_repaired": {},
            "no_repairs_needed": 0,
            "skipped_source_unavailable": 0,
            "dry_run": False,
            "details": [],
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "execution_time_seconds": 0.0,
        }

    def _is_missing(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        if isinstance(value, (int, float)):
            return value == 0
        return False

    def _normalize_url(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None

        normalized = str(url).strip()
        if not normalized:
            return None

        if normalized.startswith("https://www.autoscout24.dehttps://"):
            return normalized.replace("https://www.autoscout24.dehttps://", "https://", 1)
        if normalized.startswith("www.autoscout24.dehttps://"):
            return normalized.replace("www.autoscout24.dehttps://", "https://", 1)
        if normalized.startswith("https://www.autoscout24.de"):
            return normalized
        if normalized.startswith("www.autoscout24.de"):
            return f"https://{normalized}"
        if normalized.startswith("autoscout24.de"):
            return f"https://www.{normalized}"
        if normalized.startswith("//"):
            return f"https:{normalized}"
        if normalized.startswith("http://") and "autoscout24.de" in normalized:
            return normalized.replace("http://", "https://", 1)

        return normalized

    def _merge_value(self, current: Any, incoming: Any, field: str) -> Tuple[Any, bool, Optional[str]]:
        if self._is_missing(current) and not self._is_missing(incoming):
            return incoming, True, "POPULATED"
        if not self._is_missing(current) and self._is_missing(incoming):
            return current, False, "KEEP_EXISTING"
        if self._is_missing(current) and self._is_missing(incoming):
            return current, False, "KEEP_EXISTING"

        if field in {"description", "options_found"}:
            if isinstance(current, str) and isinstance(incoming, str) and current != incoming:
                current_words = len([word for word in current.split() if word])
                incoming_words = len([word for word in incoming.split() if word])
                if incoming_words > current_words:
                    return incoming, True, "BETTER_VALUE"
            return current, False, "KEEP_EXISTING"

        if field == "price":
            try:
                if isinstance(current, (int, float)) and isinstance(incoming, (int, float)) and incoming < current:
                    return incoming, True, "BETTER_VALUE"
            except Exception:
                pass

        if field in {"km"}:
            try:
                if isinstance(current, (int, float)) and isinstance(incoming, (int, float)) and incoming < current:
                    return incoming, True, "BETTER_VALUE"
            except Exception:
                pass

        if field in {"year"}:
            try:
                if isinstance(current, (int, float)) and isinstance(incoming, (int, float)) and incoming > current:
                    return incoming, True, "BETTER_VALUE"
            except Exception:
                pass

        if field in {"hp"}:
            try:
                if isinstance(current, (int, float)) and isinstance(incoming, (int, float)) and incoming > current:
                    return incoming, True, "BETTER_VALUE"
            except Exception:
                pass

        if isinstance(current, str) and isinstance(incoming, str) and current != incoming:
            current_words = len([word for word in current.split() if word])
            incoming_words = len([word for word in incoming.split() if word])
            if incoming_words > current_words:
                return incoming, True, "BETTER_VALUE"

        return current, False, "UNCHANGED"

    def _build_payload(self, car: Car, detail: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        payload: Dict[str, Any] = {}
        changed_fields: List[str] = []

        has_missing_field = any(
            self._is_missing(getattr(car, field, None))
            for field in [
                "price",
                "km",
                "year",
                "body_type",
                "hp",
                "drive",
                "gearbox",
                "upholstery",
                "interior_color",
                "color",
                "color_detail",
                "description",
                "options_found",
            ]
        )
        if not has_missing_field:
            return {}, []

        for field in [
            "price",
            "km",
            "year",
            "body_type",
            "hp",
            "drive",
            "gearbox",
            "upholstery",
            "interior_color",
            "color",
            "color_detail",
            "description",
            "options_found",
        ]:
            current_value = getattr(car, field, None)
            incoming_value = detail.get(field)
            if field == "options_found" and incoming_value is None:
                incoming_value = detail.get("options")
            if field == "description" and incoming_value is None:
                incoming_value = detail.get("description")
            if field == "price" and incoming_value is None and getattr(car, "price", None) is None:
                continue

            merged_value, changed, _ = self._merge_value(current_value, incoming_value, field)
            if changed:
                payload[field] = merged_value
                changed_fields.append(field)

        if not payload:
            return {}, []

        return payload, changed_fields

    def _apply_payload(self, conn: Any, car_id: int, payload: Dict[str, Any], changed_fields: List[str], dry_run: bool = False) -> bool:
        if not payload or not changed_fields:
            return False
        if dry_run:
            return False

        assignments = [f"{field} = ?" for field in changed_fields]
        values = [payload[field] for field in changed_fields] + [datetime.now().isoformat(), car_id]
        try:
            conn.execute(f"UPDATE cars SET {', '.join(assignments)}, last_modified = ? WHERE id = ?", values)
        except Exception:
            conn.rollback()
            raise
        return True

    def _fetch_details(self, car: Car, url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        try:
            lookup_url = self._normalize_url(url or car.url)
            if not lookup_url:
                return None
            detail = scraper.fetch_car_details(lookup_url)
            if not detail:
                return None
            detail.setdefault("description", scraper.fetch_description(lookup_url))
            detail.setdefault("options_found", detail.get("options", []))
            if isinstance(detail.get("options_found"), list):
                detail["options_found"] = ", ".join(detail["options_found"])
            return detail
        except Exception as exc:
            debug.warning(f"Repair fetch failed for car {car.id}: {exc}")
            return None

    def run(self, dry_run: bool = False) -> Dict[str, Any]:
        start_time = datetime.now()
        self.report = {
            "cars_checked": 0,
            "cars_analyzed": 0,
            "cars_repaired": 0,
            "cars_unchanged": 0,
            "cars_skipped": 0,
            "cars_unavailable": 0,
            "fields_repaired": {},
            "no_repairs_needed": 0,
            "skipped_source_unavailable": 0,
            "dry_run": False,
            "details": [],
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "execution_time_seconds": 0.0,
        }
        conn = database.get_connection()
        try:
            cars = database.get_all_cars()
            self.report["cars_checked"] = len(cars)
            self.report["cars_analyzed"] = len(cars)
            self.report["dry_run"] = dry_run

            for car in cars:
                try:
                    if not car.url:
                        self.report["cars_skipped"] += 1
                        continue

                    normalized_url = self._normalize_url(car.url)
                    if not normalized_url:
                        self.report["cars_skipped"] += 1
                        continue

                    detail = self._fetch_details(car, url=normalized_url)
                    if not detail:
                        self.report["cars_unavailable"] += 1
                        continue

                    payload, changed_fields = self._build_payload(car, detail)
                    if not payload:
                        self.report["cars_unchanged"] += 1
                        self.report["no_repairs_needed"] += 1
                        continue

                    wrote = self._apply_payload(conn, car.id, payload, changed_fields, dry_run=dry_run)
                    if wrote:
                        self.report["cars_repaired"] += 1
                    else:
                        self.report["cars_unchanged"] += 1
                        self.report["no_repairs_needed"] += 1
                        continue

                    self.report["details"].append({
                        "id": car.id,
                        "title": car.title,
                        "fields": changed_fields,
                    })
                    for field in changed_fields:
                        self.report["fields_repaired"][field] = self.report["fields_repaired"].get(field, 0) + 1
                except Exception as exc:
                    debug.warning(f"Repair failed for car {car.id}: {exc}")
                    self.report["cars_unavailable"] += 1
                    continue

            if not dry_run:
                database.commit(conn)

            self.report["finished_at"] = datetime.now().isoformat()
            self.report["execution_time_seconds"] = round((datetime.now() - start_time).total_seconds(), 3)
            self.report["skipped_source_unavailable"] = self.report["cars_unavailable"]
            self._persist_report()
            return self.report
        finally:
            conn.close()

    def _persist_report(self) -> None:
        conn = database.get_connection()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS repair_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, report TEXT)")
            conn.execute("INSERT INTO repair_runs (created_at, report) VALUES (?, ?)", (datetime.now().isoformat(), json.dumps(self.report)))
            conn.commit()
        finally:
            conn.close()

    def print_report(self, report: Optional[Dict[str, Any]] = None) -> None:
        report = report or self.report
        print("\n-------------------------------------------------")
        print("Enterprise Data Repair Report")
        print("-------------------------------------------------")
        print(f"Cars analysed: {report.get('cars_analyzed', report.get('cars_checked', 0))}")
        print(f"Cars repaired: {report['cars_repaired']}")
        print(f"Cars unchanged: {report.get('cars_unchanged', report.get('no_repairs_needed', 0))}")
        print(f"Cars skipped: {report.get('cars_skipped', 0)}")
        print(f"Cars unavailable: {report.get('cars_unavailable', report.get('skipped_source_unavailable', 0))}")
        print()
        print("Fields repaired:")
        for field, count in sorted(report["fields_repaired"].items()):
            print(f"  - {field}: {count}")
        print()
        print(f"Execution time: {report.get('execution_time_seconds', 0.0):.3f}s")
        if report.get("dry_run"):
            print("Dry run only - no changes were written.")


engine = RepairEngine()


def run_repair(dry_run: bool = False) -> Dict[str, Any]:
    return engine.run(dry_run=dry_run)


def _merge_value(current: Any, incoming: Any, field: str) -> Any:
    merged, _, _ = engine._merge_value(current, incoming, field)
    return merged
