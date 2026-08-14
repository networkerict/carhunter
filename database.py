"""
AutoHunter v2.4
Database module
"""

import hashlib
import json
import sqlite3
import os
from datetime import datetime

import config
import debug
from models import Car


def get_connection():

    db_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            config.DATABASE
        )
    )

    debug.info(
        f"Connecting database: {db_path}"
    )

    connection = sqlite3.connect(
        db_path
    )

    init_database(connection)

    return connection


def commit(conn=None):
    if conn is None:
        conn = get_connection()
    conn.commit()
    return conn


def test_connection():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )

    tables = cursor.fetchall()

    debug.info(
        f"Database tables: {tables}"
    )

    connection.close()

def update_source_display_name(source_name: str, display_name: str) -> None:
    """Idempotently update sources.display_name from adapter descriptor metadata.

    Called by the source registry at build time so the table always reflects
    the human-readable label each adapter declares.  No-ops when the row does
    not yet exist (it will be created on the first snapshot write).
    """
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE sources
            SET display_name = ?
            WHERE source_name = ?
              AND display_name != ?
            """,
            (display_name, source_name, display_name),
        )
        conn.commit()
    finally:
        conn.close()


def _build_source_url_map(conn):
    """Return {source_url: (source_name, display_label)} for all source_listings.

    Uses sources.display_name as the authoritative label.  Falls back to
    source_name when display_name is absent or still equals source_name (i.e.
    not yet synced by the registry).
    """
    rows = conn.execute(
        """
        SELECT sl.source_url, s.source_name, s.display_name
        FROM source_listings sl
        JOIN sources s ON s.id = sl.source_id
        """
    ).fetchall()
    result = {}
    for source_url, source_name, display_name in rows:
        if source_url:
            label = display_name if (display_name and display_name != source_name) else source_name
            result[source_url] = (source_name, label)
    return result


def _enrich_car_with_source(car, source_map):
    """Attach source_name and source_label to a Car object.

    Resolves source via cars.url -> source_listings.source_url -> sources.
    Falls back safely for rows with no resolvable URL.
    """
    car.source_name = None
    car.source_label = "Listing"
    url = getattr(car, "url", None)
    if url:
        src = source_map.get(url)
        if src:
            car.source_name = src[0]
            car.source_label = src[1]
    return car


def _enrich_cars(cars, conn):
    """Enrich a list of Car objects with source_name and source_label in one pass."""
    source_map = _build_source_url_map(conn)
    for car in cars:
        _enrich_car_with_source(car, source_map)
    return cars


def get_source_counts():
    """Return active portal inventory counts grouped by source.

    Only counts cars with sold=0 (active portal inventory).
    Uses sources.display_name as the label; falls back to source_name.
    Cars whose URL cannot be resolved to a source are excluded from counts.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT s.source_name, s.display_name, COUNT(c.id) AS cnt
            FROM cars c
            JOIN source_listings sl ON sl.source_url = c.url
            JOIN sources s ON s.id = sl.source_id
            WHERE COALESCE(c.sold, 0) = 0
            GROUP BY s.source_name, s.display_name
            ORDER BY cnt DESC
            """
        ).fetchall()
        result = {}
        for source_name, display_name, cnt in rows:
            label = display_name if (display_name and display_name != source_name) else source_name
            result[label] = cnt
        return result
    finally:
        conn.close()


def get_car(car_id):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM cars
        WHERE id = ?
        """,
        (car_id,)
    )

    car = cursor.fetchone()

    if car:
        debug.info(
            f"Car found: {car[3]}"
        )
        result = Car(car)
        source_map = _build_source_url_map(connection)
        _enrich_car_with_source(result, source_map)
        connection.close()
        return result

    else:
        connection.close()
        debug.warning(
            f"Car not found: {car_id}"
        )
        return None

def car_exists(fingerprint):

    conn = get_connection()

    result = conn.execute(
        """
        SELECT id
        FROM cars
        WHERE fingerprint = ?
        """,
        (fingerprint,)
    ).fetchone()

    conn.close()

    return result is not None



def get_all_cars():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM cars
        """
    )

    rows = cursor.fetchall()

    connection.close()

    from models import Car

    return [
        Car(row)
        for row in rows
    ]


def update_car_options(
    car_id,
    options_found,
    options_score,
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE cars
        SET
            options_found = ?,
            options_score = ?,
            options_checked = datetime('now')
        WHERE id = ?
        """,
        (
            options_found,
            options_score,
            car_id
        )
    )

    connection.commit()

    connection.close()

def database_health():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            COUNT(*),
            SUM(description != ''),
            SUM(description = ''),
            SUM(options_checked != '')
        FROM cars
        """
    )

    result = cursor.fetchone()

    connection.close()

    return {
        "total": result[0] or 0,
        "with_description": result[1] or 0,
        "missing_description": result[2] or 0,
        "options_checked": result[3] or 0
    }

def update_car_description(
    car_id,
    description
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE cars
        SET description = ?
        WHERE id = ?
        """,
        (
            description,
            car_id
        )
    )

    connection.commit()

    connection.close()


def update_car_scores(
    car_id,
    car_score,
    value_score,
    premium_score,
    final_score,
    personal_score=0,
    watchlist_match=0,
    conn=None
):

    own_connection = False

    if conn is None:
        conn = get_connection()
        own_connection = True

    conn.execute(
        """
        UPDATE cars
        SET
            car_score = ?,
            value_score = ?,
            premium_score = ?,
            final_score = ?,
            personal_score = ?,
            watchlist_match = ?
        WHERE id = ?
        """,
        (
            car_score,
            value_score,
            premium_score,
            final_score,
            personal_score,
            watchlist_match,
            car_id
        )
    )

    if own_connection:
        conn.commit()
        conn.close()
def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _hashable_value(value):
    if isinstance(value, dict):
        return {str(key): _hashable_value(val) for key, val in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_hashable_value(item) for item in value]
    if isinstance(value, tuple):
        return [_hashable_value(item) for item in value]
    if isinstance(value, set):
        return sorted(_hashable_value(item) for item in value)
    if value is None:
        return None
    return value


def _semantic_observation_payload(snapshot):
    extracted_fields = dict(getattr(snapshot, "extracted_fields", {}) or {})
    payload = {
        "source_name": getattr(snapshot, "source_name", ""),
        "source_listing_id": getattr(snapshot, "source_listing_id", ""),
        "extracted_fields": _hashable_value(extracted_fields),
        "normalized_availability": _listing_availability(snapshot),
    }
    return _hashable_value(payload)


def _snapshot_hash(snapshot):
    semantic_payload = _semantic_observation_payload(snapshot)
    return hashlib.sha256(
        _canonical_json(semantic_payload).encode("utf-8")
    ).hexdigest()


def save_source_snapshot(snapshot, *, dry_run=False, conn=None):
    """Persist a SourceSnapshot in the canonical source-listing tables.

    This is intentionally narrow: it creates the canonical source/listing and
    provenance record needed to retain SourceSnapshot identity and provenance
    before the compatibility projection writes to the legacy cars table.
    """
    if dry_run:
        return None

    if snapshot is None or not hasattr(snapshot, "source_name"):
        return None

    should_close = conn is None
    conn = conn or get_connection()
    try:
        source_name = str(getattr(snapshot, "source_name", "unknown") or "unknown").strip()
        source_listing_id = str(getattr(snapshot, "source_listing_id", "") or "")
        source_url = str(getattr(snapshot, "source_url", "") or "")
        source_row = conn.execute(
            "SELECT id FROM sources WHERE source_name = ?",
            (source_name,),
        ).fetchone()

        if source_row is None:
            conn.execute(
                """
                INSERT INTO sources (source_name, display_name, source_url, created_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (source_name, source_name, source_url),
            )
            source_id = conn.execute(
                "SELECT id FROM sources WHERE source_name = ?",
                (source_name,),
            ).fetchone()[0]
        else:
            source_id = source_row[0]

        conn.execute(
            """
            INSERT OR IGNORE INTO source_listings (
                source_id,
                source_listing_id,
                source_url,
                first_seen,
                last_seen,
                status
            ) VALUES (?, ?, ?, datetime('now'), datetime('now'), 'active')
            """,
            (source_id, source_listing_id, source_url),
        )

        listing_row = conn.execute(
            "SELECT id FROM source_listings WHERE source_id = ? AND source_listing_id = ?",
            (source_id, source_listing_id),
        ).fetchone()
        listing_id = listing_row[0]

        conn.execute(
            """
            UPDATE source_listings
            SET source_url = ?, last_seen = datetime('now'), status = 'active'
            WHERE id = ?
            """,
            (source_url, listing_id),
        )

        snapshot_hash = _snapshot_hash(snapshot)
        existing_snapshot = conn.execute(
            """
            SELECT id FROM source_snapshots
            WHERE source_id = ? AND source_listing_id = ? AND snapshot_hash = ?
            ORDER BY id DESC LIMIT 1
            """,
            (source_id, source_listing_id, snapshot_hash),
        ).fetchone()

        if existing_snapshot is not None:
            if should_close:
                conn.commit()
            return existing_snapshot[0]

        conn.execute(
            """
            INSERT INTO source_snapshots (
                source_id,
                source_listing_id,
                source_url,
                discovered_at,
                fetched_at,
                snapshot_hash,
                raw_summary_payload,
                raw_detail_payload,
                extracted_fields,
                field_provenance,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                source_id,
                source_listing_id,
                source_url,
                getattr(snapshot, "discovered_at", None).isoformat() if getattr(snapshot, "discovered_at", None) else None,
                getattr(snapshot, "fetched_at", None).isoformat() if getattr(snapshot, "fetched_at", None) else None,
                snapshot_hash,
                _canonical_json(dict(getattr(snapshot, "raw_summary_payload", {}) or {})),
                _canonical_json(dict(getattr(snapshot, "raw_detail_payload", {}) or {})) if getattr(snapshot, "raw_detail_payload", None) is not None else None,
                _canonical_json(dict(getattr(snapshot, "extracted_fields", {}) or {})),
                _canonical_json(dict(getattr(snapshot, "field_provenance", {}) or {})),
            ),
        )

        snapshot_row = conn.execute(
            "SELECT id FROM source_snapshots WHERE source_id = ? AND source_listing_id = ? AND snapshot_hash = ? ORDER BY id DESC LIMIT 1",
            (source_id, source_listing_id, snapshot_hash),
        ).fetchone()
        snapshot_row_id = snapshot_row[0]

        listing_id_for_state = _ensure_canonical_listing(snapshot, conn=conn)
        if listing_id_for_state is not None:
            _sync_listing_current_state(snapshot, listing_id_for_state, snapshot_row_id, conn=conn)

        conn.execute(
            """
            INSERT INTO source_provenance (
                source_snapshot_id,
                source_id,
                source_listing_id,
                source_url,
                source_name,
                retrieval_timestamp,
                field_provenance,
                mapping_version,
                mapping_decision,
                canonical_target,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                snapshot_row_id,
                source_id,
                source_listing_id,
                source_url,
                source_name,
                getattr(snapshot, "fetched_at", None).isoformat() if getattr(snapshot, "fetched_at", None) else (getattr(snapshot, "discovered_at", None).isoformat() if getattr(snapshot, "discovered_at", None) else None),
                _canonical_json(dict(getattr(snapshot, "field_provenance", {}) or {})),
                "arch-007-foundation",
                "persisted_snapshot",
                "source_snapshot",
            ),
        )

        if should_close:
            conn.commit()
        return snapshot_row_id
    finally:
        if should_close:
            conn.close()


def persist_source_snapshots(snapshots, *, dry_run=False):
    """Persist a batch of SourceSnapshots in canonical storage.

    The batch is committed as one transaction so a later failure rolls back
    earlier canonical writes in the same batch.
    """
    if dry_run:
        return []

    snapshot_list = list(snapshots or [])
    if not snapshot_list:
        return []

    conn = get_connection()
    try:
        conn.execute("BEGIN")
        persisted = []
        seen = set()
        for snapshot in snapshot_list:
            row_id = save_source_snapshot(snapshot, dry_run=False, conn=conn)
            if row_id is not None and row_id not in seen:
                persisted.append(row_id)
                seen.add(row_id)
        conn.commit()
        return persisted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _normalize_vin(raw_value):
    if raw_value is None:
        return None
    value = str(raw_value).strip().upper()
    value = "".join(ch for ch in value if ch.isalnum())
    return value or None


def _extract_vehicle_field(snapshot, *field_names):
    extracted = dict(getattr(snapshot, "extracted_fields", {}) or {})
    raw = dict(getattr(snapshot, "raw_summary_payload", {}) or {})
    for key in field_names:
        if key in extracted:
            return extracted.get(key)
        if key in raw:
            return raw.get(key)
    for payload in (raw, getattr(snapshot, "raw_detail_payload", {}) or {}):
        if isinstance(payload, dict):
            for key in field_names:
                if key in payload:
                    return payload.get(key)
    return None


def _extract_vin(snapshot):
    value = _extract_vehicle_field(
        snapshot,
        "vin",
        "vin_number",
        "vehicle_identification_number",
        "registration_vin",
        "vehicleVin",
    )
    return _normalize_vin(value)


def _canonical_vehicle_payload(snapshot):
    extracted = dict(getattr(snapshot, "extracted_fields", {}) or {})
    normalized = {
        "vin": _extract_vin(snapshot),
        "make": extracted.get("make") or extracted.get("brand") or extracted.get("manufacturer"),
        "model": extracted.get("model") or extracted.get("model_name"),
        "generation": extracted.get("generation") or extracted.get("model_generation"),
        "body_type": extracted.get("body_type") or extracted.get("bodyType") or extracted.get("vehicle_type"),
        "engine_variant": extracted.get("engine") or extracted.get("engine_variant") or extracted.get("motorTypeName") or extracted.get("engine_type"),
        "drivetrain": extracted.get("drive") or extracted.get("drive_train") or extracted.get("drivetrain"),
        "transmission": extracted.get("transmission") or extracted.get("gearbox") or extracted.get("transmissionType"),
        "first_registration_year": extracted.get("year") or extracted.get("first_registration_year") or extracted.get("model_year"),
    }
    for key, value in list(normalized.items()):
        if value is not None and isinstance(value, str):
            value = value.strip()
            if not value:
                normalized[key] = None
            else:
                normalized[key] = value
    return normalized


def _coerce_int(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return int(float(candidate))
        except ValueError:
            return None
    return None


def _coerce_text(value):
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        text = str(value).strip()
        return text or None
    return str(value).strip() or None


def _snapshot_time(snapshot):
    for key in ("fetched_at", "discovered_at"):
        value = getattr(snapshot, key, None)
        if value is not None:
            if hasattr(value, "isoformat"):
                return value
    return None


def _snapshot_is_newer(snapshot, latest_snapshot_id, conn):
    if latest_snapshot_id is None:
        return True
    if snapshot is None:
        return False
    current_time = _snapshot_time(snapshot)
    if current_time is None:
        return True
    row = conn.execute(
        "SELECT fetched_at, discovered_at FROM source_snapshots WHERE id = ?",
        (latest_snapshot_id,),
    ).fetchone()
    if row is None:
        return True
    latest_fetched = row[0]
    latest_discovered = row[1]
    try:
        if latest_fetched and latest_fetched != "":
            latest_dt = datetime.fromisoformat(latest_fetched)
        elif latest_discovered and latest_discovered != "":
            latest_dt = datetime.fromisoformat(latest_discovered)
        else:
            return True
    except ValueError:
        return True
    if current_time and hasattr(current_time, "isoformat"):
        return current_time >= latest_dt
    return True


def _first_snapshot_field_with_name(snapshot, *field_names, nested_keys=()):
    for mapping in (
        dict(getattr(snapshot, "extracted_fields", {}) or {}),
        dict(getattr(snapshot, "raw_summary_payload", {}) or {}),
        dict(getattr(snapshot, "raw_detail_payload", {}) or {}),
    ):
        for field_name in field_names:
            if field_name in mapping:
                value = mapping.get(field_name)
                if isinstance(value, dict) and nested_keys:
                    for nested_key in nested_keys:
                        if nested_key in value:
                            return field_name, value.get(nested_key)
                if value is not None:
                    return field_name, value
    return None, None


def _first_snapshot_field(snapshot, *field_names, nested_keys=()):
    _, value = _first_snapshot_field_with_name(snapshot, *field_names, nested_keys=nested_keys)
    return value


def _listing_availability(snapshot):
    field_name, value = _first_snapshot_field_with_name(
        snapshot,
        "availability",
        "listing_status",
        "status",
        "is_available",
        "available",
        "isAvailable",
        "available",
        "sold",
        "isSold",
        "soldStatus",
        nested_keys=("consumerPriceGross", "price_gross", "priceGross", "gross_price", "status", "sold", "available", "is_available", "isAvailable"),
    )
    if value is None:
        return "ACTIVE"
    if isinstance(value, bool):
        if field_name in {"is_available", "isAvailable", "available"}:
            return "ACTIVE" if value else "INACTIVE"
        if field_name in {"sold", "isSold", "soldStatus"}:
            return "SOLD" if value else "ACTIVE"
    normalized = str(value).strip().upper()
    if normalized in {"ACTIVE", "AVAILABLE", "TRUE", "YES", "LISTED", "OPEN"}:
        return "ACTIVE"
    if normalized in {"INACTIVE", "UNAVAILABLE", "NOT_AVAILABLE", "REMOVED", "DELETED", "FALSE", "NO"}:
        return "INACTIVE"
    if normalized in {"SOLD", "ENDED", "EXPIRED"}:
        return "SOLD"
    if normalized in {"UNKNOWN", "NULL", ""}:
        return "UNKNOWN"
    return "ACTIVE"


def _sync_listing_current_state(snapshot, listing_id, source_snapshot_id, conn=None):
    """Update the canonical listing's effective current state.

    The row stores the latest accepted SourceSnapshot for the whole listing state.
    Field-level provenance remains in source_snapshots/source_provenance and is
    not flattened into a per-field listing column.
    """
    if snapshot is None or listing_id is None:
        return False
    should_close = conn is None
    conn = conn or get_connection()

    try:
        row = conn.execute(
            """
            SELECT
                current_price,
                current_mileage,
                current_description,
                current_seller,
                current_url,
                current_options,
                availability,
                latest_source_snapshot_id
            FROM listings
            WHERE id = ?
            """,
            (listing_id,),
        ).fetchone()
        if row is None:
            return False

        current_price, current_mileage, current_description, current_seller, current_url, current_options, current_availability, latest_snapshot_id = row
        if source_snapshot_id is not None and not _snapshot_is_newer(snapshot, latest_snapshot_id, conn):
            return False

        incoming_price = _coerce_int(
            _first_snapshot_field(
                snapshot,
                "price_gross",
                "priceGross",
                "consumerPriceGross",
                "gross_price",
                "price",
                "listing_price",
                "current_price",
                nested_keys=("consumerPriceGross", "price_gross", "priceGross", "gross_price"),
            )
        )
        incoming_mileage = _coerce_int(
            _first_snapshot_field(snapshot, "km", "mileage", "mileage_in_km", "mileageInKm")
        )
        incoming_description = _coerce_text(
            _first_snapshot_field(snapshot, "description", "description_text", "listing_description")
        )
        incoming_seller = _coerce_text(
            _first_snapshot_field(snapshot, "seller", "dealer", "seller_name", "dealer_name")
        )
        incoming_url = _coerce_text(getattr(snapshot, "source_url", "") or "")
        incoming_options = _first_snapshot_field(snapshot, "options", "options_found", "equipment", "equipment_list")
        incoming_availability = _listing_availability(snapshot)

        update_values = {
            "current_price": incoming_price if incoming_price is not None else current_price,
            "current_mileage": incoming_mileage if incoming_mileage is not None else current_mileage,
            "current_description": incoming_description if incoming_description is not None else current_description,
            "current_seller": incoming_seller if incoming_seller is not None else current_seller,
            "current_url": incoming_url if incoming_url else current_url,
            "current_options": _canonical_json(incoming_options) if incoming_options is not None else current_options,
            "availability": incoming_availability if incoming_availability else (current_availability or "ACTIVE"),
            "latest_source_snapshot_id": source_snapshot_id,
        }

        conn.execute(
            """
            UPDATE listings
            SET
                current_price = ?,
                current_mileage = ?,
                current_description = ?,
                current_seller = ?,
                current_url = ?,
                current_options = ?,
                availability = ?,
                latest_source_snapshot_id = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                update_values["current_price"],
                update_values["current_mileage"],
                update_values["current_description"],
                update_values["current_seller"],
                update_values["current_url"],
                update_values["current_options"],
                update_values["availability"],
                update_values["latest_source_snapshot_id"],
                listing_id,
            ),
        )
        return True
    finally:
        if should_close:
            conn.close()


def _ensure_canonical_listing(snapshot, conn=None):
    should_close = conn is None
    conn = conn or get_connection()

    try:
        source_name = str(getattr(snapshot, "source_name", "") or "").strip()
        source_listing_id = str(getattr(snapshot, "source_listing_id", "") or "")
        source_row = conn.execute(
            "SELECT id FROM sources WHERE source_name = ?",
            (source_name,),
        ).fetchone()
        if source_row is None:
            source_id = None
        else:
            source_id = source_row[0]

        if source_id is None:
            return None

        source_listing_row = conn.execute(
            "SELECT id FROM source_listings WHERE source_id = ? AND source_listing_id = ?",
            (source_id, source_listing_id),
        ).fetchone()
        if source_listing_row is None:
            return None
        source_listing_db_id = source_listing_row[0]

        listing_row = conn.execute(
            "SELECT id, vehicle_id, status, canonical_url FROM listings WHERE source_listing_row_id = ?",
            (source_listing_db_id,),
        ).fetchone()
        if listing_row is not None:
            listing_id = listing_row[0]
            conn.execute(
                "UPDATE listings SET canonical_url = ?, updated_at = datetime('now') WHERE id = ?",
                (str(getattr(snapshot, "source_url", "") or ""), listing_id),
            )
            return listing_id

        conn.execute(
            """
            INSERT OR IGNORE INTO listings (
                source_id,
                source_listing_id,
                source_listing_row_id,
                canonical_url,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, 'active', datetime('now'), datetime('now'))
            """,
            (source_id, source_listing_id, source_listing_db_id, str(getattr(snapshot, "source_url", "") or "")),
        )
        row = conn.execute(
            "SELECT id FROM listings WHERE source_listing_row_id = ?",
            (source_listing_db_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        if should_close:
            conn.close()


def _record_mapping_provenance(conn, *, listing_id, vehicle_id, source_snapshot_id, source_id, source_listing_id, outcome, evidence, review_required=False):
    conn.execute(
        """
        INSERT INTO listing_vehicle_mappings (
            listing_id,
            vehicle_id,
            source_snapshot_id,
            source_id,
            source_listing_id,
            outcome,
            evidence,
            review_required,
            mapping_version,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'arch-007-vehicle-mapping', datetime('now'))
        """,
        (
            listing_id,
            vehicle_id,
            source_snapshot_id,
            source_id,
            source_listing_id,
            outcome,
            _canonical_json(dict(evidence or {})),
            1 if review_required else 0,
        ),
    )


def resolve_canonical_listing_and_vehicle(snapshot, *, dry_run=False, conn=None):
    """Map a SourceSnapshot to canonical Listing + Vehicle records.

    This is intentionally conservative: the current implementation only resolves
    cross-source identity via a normalized VIN. No heuristic fingerprint-based
    vehicle merging is allowed in this slice.
    """
    if dry_run:
        return None, None, "PROVISIONAL_UNRESOLVED"

    if snapshot is None or not hasattr(snapshot, "source_name"):
        return None, None, "PROVISIONAL_UNRESOLVED"

    should_close = conn is None
    conn = conn or get_connection()
    try:
        source_name = str(getattr(snapshot, "source_name", "") or "").strip()
        source_listing_id = str(getattr(snapshot, "source_listing_id", "") or "")
        source_row = conn.execute(
            "SELECT id FROM sources WHERE source_name = ?",
            (source_name,),
        ).fetchone()
        if source_row is None:
            return None, None, "PROVISIONAL_UNRESOLVED"
        source_id = source_row[0]

        source_listing_row = conn.execute(
            "SELECT id FROM source_listings WHERE source_id = ? AND source_listing_id = ?",
            (source_id, source_listing_id),
        ).fetchone()
        if source_listing_row is None:
            return None, None, "PROVISIONAL_UNRESOLVED"
        source_listing_db_id = source_listing_row[0]

        listing_row = conn.execute(
            "SELECT id, vehicle_id, status FROM listings WHERE source_listing_row_id = ?",
            (source_listing_db_id,),
        ).fetchone()
        if listing_row is None:
            conn.execute(
                """
                INSERT OR IGNORE INTO listings (
                    source_id,
                    source_listing_id,
                    source_listing_row_id,
                    canonical_url,
                    status,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, 'active', datetime('now'), datetime('now'))
                """,
                (source_id, source_listing_id, source_listing_db_id, str(getattr(snapshot, "source_url", "") or "")),
            )
            listing_row = conn.execute(
                "SELECT id, vehicle_id, status FROM listings WHERE source_listing_row_id = ?",
                (source_listing_db_id,),
            ).fetchone()

        listing_id = listing_row[0]
        current_vehicle_id = listing_row[1]
        source_snapshot_row = conn.execute(
            "SELECT id FROM source_snapshots WHERE source_id = ? AND source_listing_id = ? AND snapshot_hash = ? ORDER BY id DESC LIMIT 1",
            (source_id, source_listing_id, _snapshot_hash(snapshot)),
        ).fetchone()
        source_snapshot_id = source_snapshot_row[0] if source_snapshot_row else None

        if current_vehicle_id is not None:
            current_vehicle_row = conn.execute(
                "SELECT id, vin FROM vehicles WHERE id = ?",
                (current_vehicle_id,),
            ).fetchone()
            current_vin = current_vehicle_row[1] if current_vehicle_row else None
            vin = _extract_vin(snapshot)

            if not vin:
                _record_mapping_provenance(
                    conn,
                    listing_id=listing_id,
                    vehicle_id=current_vehicle_id,
                    source_snapshot_id=source_snapshot_id,
                    source_id=source_id,
                    source_listing_id=source_listing_id,
                    outcome="EXISTING_LISTING",
                    evidence={
                        "source_name": source_name,
                        "source_listing_id": source_listing_id,
                        "current_vehicle_id": current_vehicle_id,
                        "current_vin": current_vin,
                        "incoming_vin": None,
                    },
                    review_required=False,
                )
                return listing_id, current_vehicle_id, "EXISTING_LISTING"

            if current_vin is None:
                conflicting_vehicle = conn.execute(
                    "SELECT id, vin FROM vehicles WHERE vin = ? AND id != ?",
                    (vin, current_vehicle_id),
                ).fetchone()
                if conflicting_vehicle is not None:
                    _record_mapping_provenance(
                        conn,
                        listing_id=listing_id,
                        vehicle_id=current_vehicle_id,
                        source_snapshot_id=source_snapshot_id,
                        source_id=source_id,
                        source_listing_id=source_listing_id,
                        outcome="OPERATOR_REVIEW",
                        evidence={
                            "source_name": source_name,
                            "source_listing_id": source_listing_id,
                            "current_vehicle_id": current_vehicle_id,
                            "current_vin": current_vin,
                            "incoming_vin": vin,
                            "conflicting_vehicle_id": conflicting_vehicle[0],
                            "conflicting_vehicle_vin": conflicting_vehicle[1],
                            "reason": "authoritative_vin_conflict",
                        },
                        review_required=True,
                    )
                    return listing_id, current_vehicle_id, "OPERATOR_REVIEW"

                conn.execute(
                    "UPDATE vehicles SET vin = ?, updated_at = datetime('now') WHERE id = ?",
                    (vin, current_vehicle_id),
                )
                _record_mapping_provenance(
                    conn,
                    listing_id=listing_id,
                    vehicle_id=current_vehicle_id,
                    source_snapshot_id=source_snapshot_id,
                    source_id=source_id,
                    source_listing_id=source_listing_id,
                    outcome="MATCHED_EXISTING_VEHICLE",
                    evidence={
                        "source_name": source_name,
                        "source_listing_id": source_listing_id,
                        "current_vehicle_id": current_vehicle_id,
                        "current_vin": current_vin,
                        "incoming_vin": vin,
                        "reason": "vin_enrichment",
                    },
                    review_required=False,
                )
                return listing_id, current_vehicle_id, "MATCHED_EXISTING_VEHICLE"

            if current_vin == vin:
                _record_mapping_provenance(
                    conn,
                    listing_id=listing_id,
                    vehicle_id=current_vehicle_id,
                    source_snapshot_id=source_snapshot_id,
                    source_id=source_id,
                    source_listing_id=source_listing_id,
                    outcome="EXISTING_LISTING",
                    evidence={
                        "source_name": source_name,
                        "source_listing_id": source_listing_id,
                        "current_vehicle_id": current_vehicle_id,
                        "current_vin": current_vin,
                        "incoming_vin": vin,
                    },
                    review_required=False,
                )
                return listing_id, current_vehicle_id, "EXISTING_LISTING"

            conflicting_vehicle = conn.execute(
                "SELECT id, vin FROM vehicles WHERE vin = ? AND id != ?",
                (vin, current_vehicle_id),
            ).fetchone()
            _record_mapping_provenance(
                conn,
                listing_id=listing_id,
                vehicle_id=current_vehicle_id,
                source_snapshot_id=source_snapshot_id,
                source_id=source_id,
                source_listing_id=source_listing_id,
                outcome="OPERATOR_REVIEW",
                evidence={
                    "source_name": source_name,
                    "source_listing_id": source_listing_id,
                    "current_vehicle_id": current_vehicle_id,
                    "current_vin": current_vin,
                    "incoming_vin": vin,
                    "conflicting_vehicle_id": conflicting_vehicle[0] if conflicting_vehicle else None,
                    "conflicting_vehicle_vin": conflicting_vehicle[1] if conflicting_vehicle else None,
                    "reason": "authoritative_vin_conflict",
                },
                review_required=True,
            )
            return listing_id, current_vehicle_id, "OPERATOR_REVIEW"

        vin = _extract_vin(snapshot)
        if vin:
            vehicle_row = conn.execute(
                "SELECT id, vin FROM vehicles WHERE vin = ?",
                (vin,),
            ).fetchone()
            if vehicle_row is not None:
                vehicle_id = vehicle_row[0]
                conn.execute(
                    "UPDATE listings SET vehicle_id = ?, status = 'linked', updated_at = datetime('now') WHERE id = ?",
                    (vehicle_id, listing_id),
                )
                _record_mapping_provenance(
                    conn,
                    listing_id=listing_id,
                    vehicle_id=vehicle_id,
                    source_snapshot_id=source_snapshot_id,
                    source_id=source_id,
                    source_listing_id=source_listing_id,
                    outcome="MATCHED_EXISTING_VEHICLE",
                    evidence={"vin": vin, "source_name": source_name},
                    review_required=False,
                )
                return listing_id, vehicle_id, "MATCHED_EXISTING_VEHICLE"

            payload = _canonical_vehicle_payload(snapshot)
            vehicle_fields = (
                vin,
                payload.get("make"),
                payload.get("model"),
                payload.get("generation"),
                payload.get("body_type"),
                payload.get("engine_variant"),
                payload.get("drivetrain"),
                payload.get("transmission"),
                payload.get("first_registration_year"),
            )
            conn.execute(
                """
                INSERT INTO vehicles (
                    vin,
                    make,
                    model,
                    generation,
                    body_type,
                    engine_variant,
                    drivetrain,
                    transmission,
                    first_registration_year,
                    created_at,
                    updated_at,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 'active')
                """,
                vehicle_fields,
            )
            vehicle_id = conn.execute("SELECT id FROM vehicles WHERE vin = ? ORDER BY id DESC LIMIT 1", (vin,)).fetchone()[0]
            conn.execute(
                "UPDATE listings SET vehicle_id = ?, status = 'linked', updated_at = datetime('now') WHERE id = ?",
                (vehicle_id, listing_id),
            )
            _record_mapping_provenance(
                conn,
                listing_id=listing_id,
                vehicle_id=vehicle_id,
                source_snapshot_id=source_snapshot_id,
                source_id=source_id,
                source_listing_id=source_listing_id,
                outcome="CREATED_NEW_VEHICLE",
                evidence={"vin": vin, "source_name": source_name},
                review_required=False,
            )
            return listing_id, vehicle_id, "CREATED_NEW_VEHICLE"

        conn.execute(
            "UPDATE listings SET status = 'unresolved', updated_at = datetime('now') WHERE id = ?",
            (listing_id,),
        )
        _record_mapping_provenance(
            conn,
            listing_id=listing_id,
            vehicle_id=None,
            source_snapshot_id=source_snapshot_id,
            source_id=source_id,
            source_listing_id=source_listing_id,
            outcome="PROVISIONAL_UNRESOLVED",
            evidence={
                "source_name": source_name,
                "source_listing_id": source_listing_id,
                "missing_vin": True,
            },
            review_required=True,
        )
        return listing_id, None, "PROVISIONAL_UNRESOLVED"
    finally:
        if should_close:
            conn.close()


def resolve_canonical_vehicle_links(snapshots, *, dry_run=False):
    """Persist canonical Listing + Vehicle resolution for a batch of snapshots."""
    if dry_run:
        return []
    snapshot_list = list(snapshots or [])
    if not snapshot_list:
        return []

    conn = get_connection()
    try:
        conn.execute("BEGIN")
        results = []
        seen = set()
        for snapshot in snapshot_list:
            listing_id, vehicle_id, outcome = resolve_canonical_listing_and_vehicle(snapshot, dry_run=False, conn=conn)
            if listing_id is not None and listing_id not in seen:
                seen.add(listing_id)
                results.append({
                    "listing_id": listing_id,
                    "vehicle_id": vehicle_id,
                    "outcome": outcome,
                })
        conn.commit()
        return results
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_car(car):

    conn = None

    try:
        conn = get_connection()

        autoscout_id = car.get("id") or car.get("autoscout_id")
        fingerprint = car.get("fingerprint")

        existing = conn.execute(
            """
            SELECT id, price
            FROM cars
            WHERE fingerprint = ?
            OR autoscout_id = ?
            ORDER BY id
            LIMIT 1
            """,
            (
                fingerprint,
                autoscout_id,
            )
        ).fetchone()

        is_new = existing is None

        price_drop = 0
        last_price = existing[1] if existing else None
        alert = 0

        incoming_price = car.get("price")
        normalized_price = None

        if isinstance(incoming_price, (int, float)) and incoming_price is not None:
            normalized_price = int(incoming_price)
        elif isinstance(incoming_price, str):
            stripped = incoming_price.strip()
            if stripped:
                try:
                    normalized_price = int(float(stripped))
                except ValueError:
                    normalized_price = None

        if existing:
            old_price = existing[1]

            if old_price is not None and normalized_price is not None and normalized_price < old_price:
                last_price = old_price
                price_drop = old_price - normalized_price
                alert = 1
            elif old_price is not None and normalized_price is None:
                normalized_price = old_price
                last_price = old_price
            elif old_price is not None and normalized_price is not None and normalized_price >= old_price:
                normalized_price = normalized_price
                last_price = old_price
                price_drop = 0
                alert = 0
            elif old_price is None and normalized_price is None:
                normalized_price = None
                last_price = None

        if existing and normalized_price is None and existing[1] is not None:
            normalized_price = existing[1]

        from datetime import datetime

        now = datetime.now().isoformat()

        if existing:
            conn.execute(
                """
                UPDATE cars
                SET
                    autoscout_id = ?,
                    fingerprint = ?,
                    title = ?,
                    price = ?,
                    km = ?,
                    year = ?,
                    url = ?,
                    last_seen = ?,
                    sold = 0,
                    sold_at = '',
                    color = ?,
                    color_detail = ?,
                    upholstery = ?,
                    interior_color = ?,
                    gearbox = ?,
                    body_type = ?,
                    hp = ?,
                    drive = ?,
                    description = ?,
                    options_found = ?,
                    last_price = ?,
                    price_drop = ?,
                    alert = ?
                WHERE id = ?
                """,
                (
                    autoscout_id,
                    fingerprint,
                    car.get("title"),
                    normalized_price,
                    car.get("km"),
                    car.get("year"),
                    car.get("url"),
                    now,
                    car.get("color",""),
                    car.get("color_detail",""),
                    car.get("upholstery",""),
                    car.get("interior_color",""),
                    car.get("gearbox",""),
                    car.get("body_type",""),
                    car.get("hp",0),
                    car.get("drive",""),
                    car.get("description", ""),
                    car.get("options_found", ""),
                    last_price,
                    price_drop,
                    alert,
                    existing[0]
                )
            )
        else:
            conn.execute(
                """
                INSERT INTO cars
                (
                    autoscout_id,
                    fingerprint,
                    title,
                    price,
                    km,
                    year,
                    url,
                    first_seen,
                    last_seen,
                    color,
                    color_detail,
                    upholstery,
                    interior_color,
                    gearbox,
                    body_type,
                    hp,
                    drive,
                    description,
                    options_found,
                    last_price,
                    price_drop,
                    alert
                )

                VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    autoscout_id,
                    fingerprint,
                    car.get("title"),
                    normalized_price,
                    car.get("km"),
                    car.get("year"),
                    car.get("url"),
                    now,
                    now,
                    car.get("color",""),
                    car.get("color_detail",""),
                    car.get("upholstery",""),
                    car.get("interior_color",""),
                    car.get("gearbox",""),
                    car.get("body_type",""),
                    car.get("hp",0),
                    car.get("drive",""),
                    car.get("description", ""),
                    car.get("options_found", ""),
                    last_price,
                    price_drop,
                    alert
                )
            )

        conn.commit()
        return is_new

    except Exception:
        if conn is not None:
            conn.rollback()
        raise

    finally:
        if conn is not None:
            conn.close()




def update_car_details(
    car_id,
    color="",
    color_detail="",
    interior_color="",
    upholstery="",
    gearbox="",
    body_type="",
    hp=0,
    drive=""
):

    conn = get_connection()

    conn.execute(
        """
        UPDATE cars
        SET
            color = ?,
            color_detail = ?,
            interior_color = ?,
            upholstery = ?,
            gearbox = ?,
            body_type = ?,
            hp = ?,
            drive = ?
        WHERE id = ?
        """,
        (
            color,
            color_detail,
            interior_color,
            upholstery,
            gearbox,
            body_type,
            hp,
            drive,
            car_id
        )
    )

    conn.commit()
    conn.close()

def update_car_year(car_id, year):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE cars
        SET year = ?
        WHERE id = ?
        """,
        (
            year,
            car_id
        )
    )

    connection.commit()
    connection.close()


def ensure_column(conn, table, column, definition):

    columns = [
        row[1]
        for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    ]

    if column not in columns:

        conn.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {column} {definition}
            """
        )


def init_database(conn):

    conn.execute("""
    CREATE TABLE IF NOT EXISTS sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_name TEXT NOT NULL UNIQUE,
        display_name TEXT DEFAULT '',
        source_url TEXT DEFAULT '',
        source_type TEXT DEFAULT 'marketplace',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS source_listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER NOT NULL,
        source_listing_id TEXT NOT NULL,
        source_url TEXT DEFAULT '',
        first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active',
        UNIQUE(source_id, source_listing_id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS source_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER NOT NULL,
        source_listing_id TEXT NOT NULL,
        source_url TEXT DEFAULT '',
        discovered_at TEXT,
        fetched_at TEXT,
        snapshot_hash TEXT NOT NULL,
        raw_summary_payload TEXT,
        raw_detail_payload TEXT,
        extracted_fields TEXT,
        field_provenance TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_id, source_listing_id, snapshot_hash)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS source_provenance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_snapshot_id INTEGER NOT NULL,
        source_id INTEGER NOT NULL,
        source_listing_id TEXT NOT NULL,
        source_url TEXT DEFAULT '',
        source_name TEXT NOT NULL,
        retrieval_timestamp TEXT,
        field_provenance TEXT,
        mapping_version TEXT DEFAULT 'arch-007-foundation',
        mapping_decision TEXT DEFAULT 'persisted_snapshot',
        canonical_target TEXT DEFAULT 'source_snapshot',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vin TEXT,
        make TEXT,
        model TEXT,
        generation TEXT,
        body_type TEXT,
        engine_variant TEXT,
        drivetrain TEXT,
        transmission TEXT,
        first_registration_year INTEGER,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(vin)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER NOT NULL,
        source_listing_id TEXT NOT NULL,
        source_listing_row_id INTEGER NOT NULL,
        vehicle_id INTEGER,
        canonical_url TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        current_price INTEGER,
        current_mileage INTEGER,
        current_description TEXT,
        current_seller TEXT,
        current_url TEXT,
        current_options TEXT,
        availability TEXT DEFAULT 'UNKNOWN',
        latest_source_snapshot_id INTEGER,
        current_state_updated_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_listing_row_id),
        UNIQUE(source_id, source_listing_id),
        FOREIGN KEY (source_listing_row_id) REFERENCES source_listings(id),
        FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
    )
    """)

    for column, definition in [
        ("current_price", "INTEGER"),
        ("current_mileage", "INTEGER"),
        ("current_description", "TEXT"),
        ("current_seller", "TEXT"),
        ("current_url", "TEXT"),
        ("current_options", "TEXT"),
        ("availability", "TEXT DEFAULT 'UNKNOWN'"),
        ("latest_source_snapshot_id", "INTEGER"),
        ("current_state_updated_at", "TEXT"),
    ]:
        ensure_column(conn, "listings", column, definition)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS listing_vehicle_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id INTEGER NOT NULL,
        vehicle_id INTEGER,
        source_snapshot_id INTEGER,
        source_id INTEGER,
        source_listing_id TEXT,
        outcome TEXT NOT NULL,
        evidence TEXT,
        review_required INTEGER DEFAULT 0,
        mapping_version TEXT DEFAULT 'arch-007-vehicle-mapping',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (listing_id) REFERENCES listings(id),
        FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        autoscout_id TEXT,
        fingerprint TEXT UNIQUE,
        title TEXT,
        price INTEGER,
        km INTEGER,
        year TEXT,
        car_score INTEGER DEFAULT 0,
        value_score INTEGER DEFAULT 0,
        final_score INTEGER DEFAULT 0,
        url TEXT,
        first_seen TEXT,
        last_seen TEXT,
        options_score INTEGER DEFAULT 0,
        options_found TEXT DEFAULT '',
        status TEXT DEFAULT 'new',
        last_price INTEGER,
        price_drop INTEGER DEFAULT 0,
        alert INTEGER DEFAULT 0,
        recommendation TEXT DEFAULT '',
        deal_score INTEGER DEFAULT 0,
        options_checked TEXT DEFAULT '',
        description TEXT DEFAULT '',
        premium_score INTEGER DEFAULT 0,
        sold INTEGER DEFAULT 0,
        sold_at TEXT DEFAULT '',
        color TEXT DEFAULT '',
        color_detail TEXT DEFAULT '',
        upholstery TEXT DEFAULT '',
        interior_color TEXT DEFAULT '',
        gearbox TEXT DEFAULT '',
        body_type TEXT DEFAULT '',
        hp INTEGER DEFAULT 0,
        drive TEXT DEFAULT '',
        options_checked_at TEXT DEFAULT '',
        personal_score INTEGER DEFAULT 0,
        watchlist_match INTEGER DEFAULT 0,
        telegram_sent INTEGER DEFAULT 0,
        telegram_sent_at TEXT DEFAULT '',
        roof_color TEXT DEFAULT '',
        last_modified TEXT DEFAULT ''
    )
    """)

    # Veilige migraties voor bestaande databases.
    car_columns = [
        ("car_score", "INTEGER DEFAULT 0"),
        ("value_score", "INTEGER DEFAULT 0"),
        ("final_score", "INTEGER DEFAULT 0"),
        ("options_score", "INTEGER DEFAULT 0"),
        ("options_found", "TEXT DEFAULT ''"),
        ("status", "TEXT DEFAULT 'new'"),
        ("last_price", "INTEGER"),
        ("price_drop", "INTEGER DEFAULT 0"),
        ("alert", "INTEGER DEFAULT 0"),
        ("recommendation", "TEXT DEFAULT ''"),
        ("deal_score", "INTEGER DEFAULT 0"),
        ("options_checked", "TEXT DEFAULT ''"),
        ("description", "TEXT DEFAULT ''"),
        ("premium_score", "INTEGER DEFAULT 0"),
        ("sold", "INTEGER DEFAULT 0"),
        ("sold_at", "TEXT DEFAULT ''"),
        ("last_modified", "TEXT DEFAULT ''"),
    ]

    for column, definition in car_columns:
        ensure_column(conn, "cars", column, definition)

    conn.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_cars_autoscout_id
    ON cars(autoscout_id)
    """)

    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_year
    ON cars(year)
    """)

    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_score
    ON cars(final_score DESC)
    """)

    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_options
    ON cars(options_score DESC)
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at DATETIME,
        finished_at DATETIME,
        status TEXT,
        new_cars INTEGER DEFAULT 0,
        not_available_anymore INTEGER DEFAULT 0,
        descriptions_updated INTEGER DEFAULT 0,
        options_updated INTEGER DEFAULT 0,
        deal_scores_updated INTEGER DEFAULT 0,
        high_score_cars INTEGER DEFAULT 0,
        price_drops INTEGER DEFAULT 0,
        alerts_sent INTEGER DEFAULT 0,
        duration_seconds INTEGER,
        error_message TEXT
    )
    """)

    # Veilige migraties voor bestaande pipeline-overzichten.
    pipeline_columns = [
        ("finished_at", "DATETIME"),
        ("status", "TEXT"),
        ("new_cars", "INTEGER DEFAULT 0"),
        ("not_available_anymore", "INTEGER DEFAULT 0"),
        ("descriptions_updated", "INTEGER DEFAULT 0"),
        ("options_updated", "INTEGER DEFAULT 0"),
        ("deal_scores_updated", "INTEGER DEFAULT 0"),
        ("high_score_cars", "INTEGER DEFAULT 0"),
        ("price_drops", "INTEGER DEFAULT 0"),
        ("alerts_sent", "INTEGER DEFAULT 0"),
        ("duration_seconds", "INTEGER"),
        ("error_message", "TEXT"),
    ]

    for column, definition in pipeline_columns:
        ensure_column(conn, "pipeline_runs", column, definition)

    conn.commit()


def get_todays_cars(limit=20):

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM cars
        WHERE DATE(first_seen) = DATE('now')
        ORDER BY
            personal_score DESC,
            final_score DESC,
            deal_score DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    cars = [Car(row) for row in rows]
    _enrich_cars(cars, conn)
    conn.close()
    return cars




def get_recent_cars(days=7, limit=20):

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM cars
        WHERE first_seen >= datetime('now', ?)
        ORDER BY
            personal_score DESC,
            final_score DESC,
            deal_score DESC
        LIMIT ?
        """,
        (
            f"-{days} days",
            limit
        )
    ).fetchall()

    cars = [Car(row) for row in rows]
    _enrich_cars(cars, conn)
    conn.close()
    return cars


def get_ranked_cars(limit=10):

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM cars
        ORDER BY
            personal_score DESC,
            final_score DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    cars = [Car(row) for row in rows]
    _enrich_cars(cars, conn)
    conn.close()
    return cars


def get_recommendation_candidates(limit=5):

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM cars
        ORDER BY
            final_score DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    conn.close()

    return [
        Car(row)
        for row in rows
    ]



def get_ranking(limit=10):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM cars
        WHERE COALESCE(sold, 0) = 0
        ORDER BY
            personal_score DESC,
            final_score DESC
        LIMIT ?
        """,
        (limit,)
    )

    rows = cursor.fetchall()
    cars = [Car(row) for row in rows]
    _enrich_cars(cars, connection)
    connection.close()
    return cars



def search_cars(
        max_price=None,
        min_year=None,
        max_km=None,
        min_score=None,
        search=None,
        colors=None,
        color_details=None,
        options=None
):

    conn = get_connection()

    query = """
    SELECT *
    FROM cars
    WHERE 1=1
    AND COALESCE(sold, 0) = 0
    """

    params = []


    if max_price:
        query += " AND price <= ?"
        params.append(max_price)


    if min_year:
        query += " AND year >= ?"
        params.append(str(min_year))


    if max_km:
        query += " AND km <= ?"
        params.append(max_km)


    if min_score:
        query += " AND final_score >= ?"
        params.append(min_score)


    if search:

        query += """
        AND title LIKE ?
        """

        params.append(
            f"%{search}%"
        )


    # nieuwe kleurfilter

    if colors:

        placeholders = ",".join(
            ["?"] * len(colors)
        )

        query += f"""
        AND color IN ({placeholders})
        """

        params.extend(colors)


    # specifieke kleurfilter

    if color_details:

        placeholders = ",".join(
            ["?"] * len(color_details)
        )

        query += f"""
        AND color_detail IN ({placeholders})
        """

        params.extend(color_details)


    # optie zoeken in bestaande options_found

    if options:

        for option in options:
            query += """
            AND options_found LIKE ?
            """

            params.append(
                f"%{option}%"
            )

    query += """
    ORDER BY
        personal_score DESC,
        final_score DESC
    """


    rows = conn.execute(
        query,
        params
    ).fetchall()

    from models import Car
    cars = [Car(row) for row in rows]
    _enrich_cars(cars, conn)
    conn.close()
    return cars


def get_inventory_counts():

    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            SUM(COALESCE(sold, 0) = 0) AS active,
            SUM(COALESCE(sold, 0) = 0 AND DATE(first_seen) = DATE('now')) AS new,
            SUM(COALESCE(sold, 0) = 1) AS sold
        FROM cars
        """
    ).fetchone()

    conn.close()

    return {
        "active": int(row[0] or 0),
        "new": int(row[1] or 0),
        "sold": int(row[2] or 0),
    }


def get_option_counts(limit=None):

    conn = get_connection()


    rows = conn.execute("""
        SELECT options_found
        FROM cars
        WHERE options_found != ''
    """).fetchall()


    conn.close()


    counts = {}


    for row in rows:

        options = row[0]

        if not options:
            continue


        for option in options.split(","):

            option = option.strip()


            if len(option) < 3:
                continue


            counts[option] = counts.get(option,0) + 1

    sorted_counts = sorted(
        counts.items(),
        key=lambda x: x[0].lower()
    )

    if limit is None:
        return sorted_counts

    return sorted_counts[:limit]


def get_color_detail_counts(limit=None):

    conn = get_connection()

    rows = conn.execute("""
        SELECT color_detail
        FROM cars
        WHERE color_detail != ''
    """).fetchall()

    conn.close()

    counts = {}

    for row in rows:

        color = row[0].strip()

        if len(color) < 3:
            continue

        counts[color] = counts.get(color,0) + 1

    sorted_counts = sorted(
        counts.items(),
        key=lambda x: x[0].lower()
    )

    if limit is None:
        return sorted_counts

    return sorted_counts[:limit]

def get_all_cars(conn=None):

    own_connection = False

    if conn is None:
        conn = get_connection()
        own_connection = True

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM cars
        """
    )

    rows = cursor.fetchall()

    if own_connection:
        conn.close()

    return [
        Car(row)
        for row in rows
    ]


def update_car_deal_score(car_id, score):

    conn = get_connection()

    conn.execute(
        """
        UPDATE cars
        SET deal_score = ?
        WHERE id = ?
        """,
        (
            score,
            car_id
        )
    )

    conn.commit()
    conn.close()


def get_deals(limit=20):

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM cars
        WHERE deal_score > 0
        AND watchlist_match = 1
        AND COALESCE(sold, 0) = 0
        ORDER BY
            personal_score DESC,
            deal_score DESC,
            final_score DESC
        LIMIT ?
        """,
        (
            limit,
        )
    ).fetchall()

    cars = [Car(row) for row in rows]
    _enrich_cars(cars, conn)
    conn.close()
    return cars


def get_unsent_watchlist_matches():

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM cars
        WHERE watchlist_match = 1
        AND telegram_sent = 0
        AND COALESCE(sold, 0) = 0
        ORDER BY
            personal_score DESC,
            final_score DESC
        """
    ).fetchall()

    conn.close()

    return [
        Car(row)
        for row in rows
    ]

def mark_watchlist_sent(car_id):

    conn = get_connection()

    conn.execute(
        """
        UPDATE cars
        SET
            telegram_sent = 1,
            telegram_sent_at = datetime('now')
        WHERE id = ?
        """,
        (car_id,)
    )

    conn.commit()

    conn.close()


def mark_missing_cars_sold(active_fingerprints):

    conn = get_connection()

    active_fingerprints = [fp for fp in active_fingerprints if fp]

    if not active_fingerprints:
        cursor = conn.execute(
            """
            UPDATE cars
            SET sold = 1,
                sold_at = datetime('now')
            WHERE COALESCE(sold, 0) = 0
            """
        )
    else:
        placeholders = ",".join(["?"] * len(active_fingerprints))
        cursor = conn.execute(
            f"""
            UPDATE cars
            SET sold = 1,
                sold_at = datetime('now')
            WHERE fingerprint NOT IN ({placeholders})
            AND COALESCE(sold, 0) = 0
            """,
            active_fingerprints
        )

    conn.commit()
    conn.close()

    return cursor.rowcount


def mark_car_active(car_id):

    conn = get_connection()

    conn.execute(
        """
        UPDATE cars
        SET sold = 0,
            sold_at = ''
        WHERE id = ?
        """,
        (car_id,)
    )

    conn.commit()
    conn.close()


def mark_car_active(car_id):

    conn = get_connection()

    conn.execute(
        """
        UPDATE cars
        SET sold = 0,
            sold_at = ''
        WHERE id = ?
        """,
        (car_id,)
    )

    conn.commit()
    conn.close()
