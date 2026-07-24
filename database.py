"""
AutoHunter v2.4
Database module
"""

import sqlite3
import os

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

    connection.close()

    if car:
        debug.info(
            f"Car found: {car[3]}"
        )

        return Car(car)

    else:
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
def save_car(car):

    conn = get_connection()

    existing = conn.execute(
        """
        SELECT id, price
        FROM cars
        WHERE fingerprint = ?
        """,
        (
            car.get("fingerprint"),
        )
    ).fetchone()


    is_new = existing is None

    price_drop = 0
    last_price = existing[1] if existing else None
    alert = 0

    if existing:

        old_price = existing[1]
        new_price = car.get("price")

        if old_price and new_price and new_price < old_price:

            last_price = old_price
            price_drop = old_price - new_price
            alert = 1


    from datetime import datetime

    now = datetime.now().isoformat()


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
            last_price,
            price_drop,
            alert
        )

        VALUES
        (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)

        ON CONFLICT(fingerprint)

        DO UPDATE SET

            title=excluded.title,
            price=excluded.price,
            km=excluded.km,
            year=excluded.year,
            url=excluded.url,
            last_seen=excluded.last_seen,
            sold=0,
            sold_at='',
            color=excluded.color,
            color_detail=excluded.color_detail,
            upholstery=excluded.upholstery,
            interior_color=excluded.interior_color,
            gearbox=excluded.gearbox,
            body_type=excluded.body_type,
            hp=excluded.hp,
            drive=excluded.drive,
            last_price=excluded.last_price,
            price_drop=excluded.price_drop,
            alert=excluded.alert

        """,
        (
            car.get("id"),
            car.get("fingerprint"),
            car.get("title"),
            car.get("price"),
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
            last_price,
            price_drop,
            alert
        )

    )


    conn.commit()
    conn.close()

    return is_new




def update_car_details(
    car_id,
    color="",
    color_detail="",
    interior_color=""
):

    conn = get_connection()

    conn.execute(
        """
        UPDATE cars
        SET
            color = ?,
            color_detail = ?,
            interior_color = ?
        WHERE id = ?
        """,
        (
            color,
            color_detail,
            interior_color,
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

    conn.commit()
    conn.close()

    return is_new


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
        roof_color TEXT DEFAULT ''
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

    conn.close()

    return [
        Car(row)
        for row in rows
    ]




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

    conn.close()

    return [
        Car(row)
        for row in rows
    ]


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

    conn.close()

    return [
        Car(row)
        for row in rows
    ]


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
        ORDER BY
            personal_score DESC,
            final_score DESC
        LIMIT ?
        """,
        (limit,)
    )

    rows = cursor.fetchall()

    connection.close()

    return [
        Car(row)
        for row in rows
    ]



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


    conn.close()


    from models import Car

    return [
        Car(row)
        for row in rows
    ]


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


def get_option_counts(limit=25):

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

    return sorted(
        counts.items(),
        key=lambda x: x[0].lower()
    )[:limit]


def get_color_detail_counts(limit=25):

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

    return sorted(
        counts.items(),
        key=lambda x: x[0].lower()
    )[:limit]

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

    conn.close()

    return [
        Car(row)
        for row in rows
    ]


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
        conn.execute(
            """
            UPDATE cars
            SET sold = 1,
                sold_at = datetime('now')
            WHERE COALESCE(sold, 0) = 0
            """
        )
    else:
        placeholders = ",".join(["?"] * len(active_fingerprints))
        conn.execute(
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
