"""
AutoHunter v3.0
Data quality and historical backfill subsystem.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import config
import database
import debug
import scraper
import repair_engine
from models import Car


@dataclass
class BackfillReport:
    processed: int = 0
    updated: int = 0
    fields_updated: int = 0
    errors: int = 0
    execution_time_seconds: float = 0.0
    success_rate: float = 0.0
    completeness_before: float = 0.0
    completeness_after: float = 0.0
    dry_run: bool = False
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: Optional[str] = None
    details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "processed": self.processed,
            "updated": self.updated,
            "fields_updated": self.fields_updated,
            "errors": self.errors,
            "execution_time_seconds": round(self.execution_time_seconds, 2),
            "success_rate": round(self.success_rate, 2),
            "completeness_before": round(self.completeness_before, 2),
            "completeness_after": round(self.completeness_after, 2),
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "details": self.details,
        }


class BackfillEngine:
    """Reusable historical backfill engine for filling missing specification data."""

    SPEC_FIELDS = [
        "body_type",
        "hp",
        "drive",
        "gearbox",
        "upholstery",
        "interior_color",
        "color",
        "color_detail",
    ]

    OPTIONAL_FIELDS = {
        "body_type": "Optional field",
        "hp": "Optional field",
        "drive": "Optional field",
        "gearbox": "Optional field",
        "upholstery": "Optional field",
        "interior_color": "Optional field",
        "color": "Optional field",
        "color_detail": "Optional field",
        "description": "Optional field",
        "options": "Optional field",
    }

    def __init__(self, state_path: Optional[str] = None):
        database_path = os.path.abspath(config.DATABASE)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", database_path)
        default_state_path = os.path.join(os.path.dirname(__file__), "logs", f"backfill_state_{safe_name}.json")
        self.state_path = state_path or default_state_path
        self._ensure_state_path()

    def _ensure_state_path(self) -> None:
        directory = os.path.dirname(self.state_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def _load_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_path):
            return {"last_id": 0, "completed_ids": []}
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            debug.warning(f"Backfill state unreadable: {exc}")
            return {"last_id": 0, "completed_ids": []}

    def _save_state(self, state: Dict[str, Any]) -> None:
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)

    def _is_missing(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        if isinstance(value, (int, float)):
            return value == 0
        return False

    def _should_update(self, current: Any, incoming: Any) -> bool:
        if self._is_missing(current) and not self._is_missing(incoming):
            return True
        return False

    def _build_update_payload(self, car: Car, detail: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self._should_update(car.body_type, detail.get("body_type")):
            payload["body_type"] = detail.get("body_type", "")
        if self._should_update(car.hp, detail.get("hp")):
            payload["hp"] = detail.get("hp", 0)
        if self._should_update(car.drive, detail.get("drive")):
            payload["drive"] = detail.get("drive", "")
        if self._should_update(car.gearbox, detail.get("gearbox")):
            payload["gearbox"] = detail.get("gearbox", "")
        if self._should_update(car.upholstery, detail.get("upholstery")):
            payload["upholstery"] = detail.get("upholstery", "")
        if self._should_update(car.interior_color, detail.get("interior_color")):
            payload["interior_color"] = detail.get("interior_color", "")
        if self._should_update(car.color, detail.get("color")):
            payload["color"] = detail.get("color", "")
        if self._should_update(car.color_detail, detail.get("color_detail")):
            payload["color_detail"] = detail.get("color_detail", "")
        if self._should_update(car.description, detail.get("description")):
            payload["description"] = detail.get("description", "")
        if self._should_update(car.options_found, detail.get("options_found")):
            payload["options_found"] = detail.get("options_found", "")
        return payload

    def _apply_updates(self, car_id: int, payload: Dict[str, Any], dry_run: bool = False) -> bool:
        if not payload:
            return False
        if dry_run:
            return False
        conn = database.get_connection()
        try:
            assignments = [f"{field} = ?" for field in payload.keys()]
            values = list(payload.values()) + [car_id]
            conn.execute(
                f"UPDATE cars SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
            conn.commit()
            return True
        except Exception as exc:
            conn.rollback()
            debug.error(f"Backfill update failed for car {car_id}: {exc}")
            return False
        finally:
            conn.close()

    def _fetch_car_details(self, car: Car) -> Optional[Dict[str, Any]]:
        try:
            detail = scraper.fetch_car_details(car.url)
            if not detail:
                return None
            detail.setdefault("description", scraper.fetch_description(car.url))
            return detail
        except Exception as exc:
            debug.warning(f"Unable to fetch details for car {car.id}: {exc}")
            return None

    def run_backfill(self, limit: int = 100, batch_size: int = 20, dry_run: bool = False, resume: bool = True) -> Dict[str, Any]:
        report = BackfillReport(dry_run=dry_run)
        started = time.time()
        state = self._load_state()
        if resume:
            last_id = state.get("last_id", 0)
        else:
            last_id = 0
            state = {"last_id": 0, "completed_ids": []}
        conn = database.get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM cars WHERE id > ? ORDER BY id LIMIT ?",
                (last_id, limit),
            ).fetchall()
            for row in rows:
                car = Car(row)
                if car.id in state.get("completed_ids", []):
                    continue
                report.processed += 1
                detail = self._fetch_car_details(car)
                if not detail:
                    report.errors += 1
                    state.setdefault("completed_ids", []).append(car.id)
                    self._save_state(state)
                    continue
                payload = self._build_update_payload(car, detail)
                if not payload:
                    state.setdefault("completed_ids", []).append(car.id)
                    self._save_state(state)
                    continue
                updated = self._apply_updates(car.id, payload, dry_run=dry_run)
                if updated:
                    report.updated += 1
                    report.fields_updated += len(payload)
                report.details.append({
                    "id": car.id,
                    "autoscout_id": car.autoscout_id,
                    "updated": updated,
                    "fields": list(payload.keys()),
                })
                state["last_id"] = car.id
                state.setdefault("completed_ids", []).append(car.id)
                self._save_state(state)
                if batch_size and report.processed % batch_size == 0:
                    debug.info(f"Backfill progress: processed {report.processed} vehicles")
        finally:
            conn.close()
        report.execution_time_seconds = time.time() - started
        if report.processed:
            report.success_rate = round((report.updated / report.processed) * 100, 2)
        else:
            report.success_rate = 0.0
        report.completeness_before = get_database_completeness()["percentage"]
        report.completeness_after = get_database_completeness()["percentage"]
        report.finished_at = datetime.now().isoformat()
        return report.to_dict()


def get_database_completeness() -> Dict[str, Any]:
    conn = database.get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0] or 0
        if not total:
            return {"total": 0, "filled": 0, "percentage": 0.0}
        filled = conn.execute(
            "SELECT COUNT(*) FROM cars WHERE title != '' AND price IS NOT NULL AND year != '' AND km IS NOT NULL AND body_type != '' AND gearbox != '' AND drive != '' AND hp > 0 AND color != '' AND color_detail != '' AND upholstery != '' AND interior_color != ''"
        ).fetchone()[0] or 0
        percentage = round((filled / total) * 100, 2) if total else 0.0
        return {"total": total, "filled": filled, "percentage": percentage}
    finally:
        conn.close()


def get_dashboard_summary() -> Dict[str, Any]:
    conn = database.get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0] or 0
        complete = conn.execute(
            "SELECT COUNT(*) FROM cars WHERE title != '' AND price IS NOT NULL AND year != '' AND km IS NOT NULL AND body_type != '' AND gearbox != '' AND drive != '' AND hp > 0 AND color != '' AND color_detail != '' AND upholstery != '' AND interior_color != ''"
        ).fetchone()[0] or 0
        incomplete = total - complete
        missing_descriptions = conn.execute("SELECT COUNT(*) FROM cars WHERE description = ''").fetchone()[0] or 0
        missing_options = conn.execute("SELECT COUNT(*) FROM cars WHERE options_found = ''").fetchone()[0] or 0
        missing_specifications = conn.execute(
            "SELECT COUNT(*) FROM cars WHERE body_type = '' OR gearbox = '' OR drive = '' OR hp <= 0 OR color = '' OR color_detail = '' OR upholstery = '' OR interior_color = ''"
        ).fetchone()[0] or 0
    finally:
        conn.close()

    repair_summary = get_repair_summary()

    return {
        "total_vehicles": total,
        "complete_vehicles": complete,
        "incomplete_vehicles": incomplete,
        "missing_descriptions": missing_descriptions,
        "missing_options": missing_options,
        "missing_specifications": missing_specifications,
        "overall_health": round((complete / total) * 100, 2) if total else 0.0,
        "historical_completeness": round((complete / total) * 100, 2) if total else 0.0,
        "repairable_issues": repair_summary["repairable_issues"],
        "repaired_today": repair_summary["repaired_today"],
        "last_repair_run": repair_summary["last_repair_run"],
        "repair_history": repair_summary["repair_history"],
        "todays_imports": 0,
        "todays_updated_vehicles": 0,
        "last_pipeline_run": None,
        "last_backfill_run": None,
        "field_summary": get_field_summary(),
    }


def get_field_summary() -> List[Dict[str, Any]]:
    conn = database.get_connection()
    try:
        fields = [
            ("title", "title"),
            ("price", "price"),
            ("year", "year"),
            ("km", "km"),
            ("body_type", "body_type"),
            ("gearbox", "gearbox"),
            ("drive", "drive"),
            ("hp", "hp"),
            ("color", "color"),
            ("color_detail", "color_detail"),
            ("upholstery", "upholstery"),
            ("interior_color", "interior_color"),
            ("description", "description"),
            ("options", "options_found"),
        ]
        rows = []
        total = conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0] or 0
        for label, column in fields:
            filled = conn.execute(
                f"SELECT COUNT(*) FROM cars WHERE {column} IS NOT NULL AND TRIM(COALESCE({column}, '')) != '' AND ({column} != 0 OR {column} != '')"
            ).fetchone()[0] or 0
            percent = round((filled / total) * 100, 2) if total else 0.0
            rows.append({
                "field": label,
                "filled": filled,
                "missing": total - filled,
                "percentage": percent,
            })
        return rows
    finally:
        conn.close()


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (int, float)):
        return value == 0
    return False


def run_integrity_checks() -> Dict[str, Any]:
    conn = database.get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0] or 0
        expected_missing = 0
        unexpected_missing = 0
        issues = []
        optional_fields = {"body_type", "gearbox", "drive", "hp", "color", "color_detail", "upholstery", "interior_color", "description", "options"}
        for row in conn.execute("SELECT id, title, price, year, km, body_type, gearbox, drive, hp, color, color_detail, upholstery, interior_color, description, options_found, final_score, value_score, car_score FROM cars"):
            car_id = row[0]
            values = {
                "title": row[1],
                "price": row[2],
                "year": row[3],
                "km": row[4],
                "body_type": row[5],
                "gearbox": row[6],
                "drive": row[7],
                "hp": row[8],
                "color": row[9],
                "color_detail": row[10],
                "upholstery": row[11],
                "interior_color": row[12],
                "description": row[13],
                "options": row[14],
                "scores": row[15] + row[16] + row[17],
            }
            for field, value in values.items():
                if field in optional_fields:
                    if _is_missing_value(value):
                        expected_missing += 1
                        issues.append({"car_id": car_id, "field": field, "classification": "Expected missing (Optional field)", "value": None})
                elif field == "scores" and _is_missing_value(value):
                    continue
                elif _is_missing_value(value):
                    unexpected_missing += 1
                    issues.append({"car_id": car_id, "field": field, "classification": "Unexpected missing (Pipeline issue)", "value": None})
        return {
            "summary": {
                "total_vehicles": total,
                "expected_missing": expected_missing,
                "unexpected_missing": unexpected_missing,
            },
            "issues": issues,
        }
    finally:
        conn.close()


def get_latest_pipeline_run() -> Optional[Dict[str, Any]]:
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT id, started_at, finished_at, status FROM pipeline_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "started_at": row[1], "finished_at": row[2], "status": row[3]}
    finally:
        conn.close()


def get_repair_summary() -> Dict[str, Any]:
    conn = database.get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS repair_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, report TEXT)")
        repairable_issues = conn.execute(
            "SELECT COUNT(*) FROM cars WHERE price IS NULL OR km IS NULL OR hp <= 0 OR gearbox = '' OR drive = '' OR body_type = '' OR upholstery = '' OR interior_color = '' OR color = '' OR color_detail = '' OR description = '' OR options_found = ''"
        ).fetchone()[0] or 0
        repaired_today = conn.execute(
            "SELECT COUNT(*) FROM repair_runs WHERE DATE(created_at) = DATE('now')"
        ).fetchone()[0] or 0
        last_row = conn.execute(
            "SELECT created_at, report FROM repair_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if last_row:
            last_repair_run = {"created_at": last_row[0], "report": json.loads(last_row[1])}
        else:
            last_repair_run = None
        history = []
        for row in conn.execute("SELECT created_at, report FROM repair_runs ORDER BY id DESC LIMIT 5"):
            history.append({"created_at": row[0], "report": json.loads(row[1])})
    finally:
        conn.close()
    return {
        "repairable_issues": repairable_issues,
        "repaired_today": repaired_today,
        "last_repair_run": last_repair_run,
        "repair_history": history,
    }


def save_backfill_report(report: Dict[str, Any]) -> None:
    conn = database.get_connection()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS backfill_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, report TEXT)"
        )
        conn.execute(
            "INSERT INTO backfill_runs (created_at, report) VALUES (?, ?)",
            (datetime.now().isoformat(), json.dumps(report)),
        )
        conn.commit()
    finally:
        conn.close()
