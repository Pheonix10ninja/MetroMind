import os
import sqlite3
import logging
from datetime import datetime

DB_PATH = os.getenv("METROMIND_DB", "/workspaces/MetroMind/metromind_memory.sqlite")

# Hard bounds (quick obvious glitch filter)
MIN_SECONDS = int(os.getenv("PHASE5_MIN_SECONDS", "10"))
MAX_SECONDS = int(os.getenv("PHASE5_MAX_SECONDS", "1800"))  # 30 minutes per stop hop

# Robust outlier filter settings
MAD_Z_CUTOFF = float(os.getenv("PHASE5_MAD_Z_CUTOFF", "6.0"))  # 6 is fairly lenient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_phase5_tables(conn: sqlite3.Connection):
    # Cleaned segments table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS segments_clean (
        id INTEGER PRIMARY KEY,                  -- same as raw segments.id
        route_id TEXT,
        direction_id TEXT,
        vehicle_ref TEXT,
        trip_id TEXT,
        from_stop_id TEXT NOT NULL,
        to_stop_id TEXT NOT NULL,
        depart_time_utc TEXT NOT NULL,
        arrive_time_utc TEXT NOT NULL,
        travel_time_seconds INTEGER NOT NULL,

        -- derived time categories
        day_of_week INTEGER NOT NULL,            -- 0=Mon ... 6=Sun (UTC based)
        hour_of_day INTEGER NOT NULL,            -- 0..23 (UTC based)
        time_bucket TEXT NOT NULL,               -- e.g. "Mon-17"

        -- cleaning metadata
        is_outlier INTEGER NOT NULL              -- 0/1
    )
    """)

    # Per-segment-key stats / coverage
    conn.execute("""
    CREATE TABLE IF NOT EXISTS segment_stats (
        route_id TEXT,
        direction_id TEXT,
        from_stop_id TEXT,
        to_stop_id TEXT,
        day_of_week INTEGER,
        hour_of_day INTEGER,
        time_bucket TEXT,

        sample_count INTEGER NOT NULL,
        median_seconds REAL,
        mad_seconds REAL,
        p10_seconds REAL,
        p90_seconds REAL,

        PRIMARY KEY (route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day)
    )
    """)
    conn.commit()


def build_clean_and_stats(conn: sqlite3.Connection):
    """
    Pipeline:
    1) Build a temp working table with derived time buckets.
    2) Hard-filter impossible values.
    3) Compute robust stats per (route, dir, from, to, day, hour).
    4) Mark outliers using modified z-score with MAD.
    5) Write segments_clean + segment_stats.
    """

    # 0) temp working table from raw segments
    conn.execute("DROP TABLE IF EXISTS segments_work;")

    # day_of_week/hour_of_day in UTC derived from arrive_time_utc (you could also use depart_time_utc)
    conn.execute(f"""
    CREATE TEMP TABLE segments_work AS
    SELECT
        id,
        COALESCE(route_id, '') AS route_id,
        COALESCE(direction_id, '') AS direction_id,
        COALESCE(vehicle_ref, '') AS vehicle_ref,
        COALESCE(trip_id, '') AS trip_id,
        from_stop_id,
        to_stop_id,
        depart_time_utc,
        arrive_time_utc,
        travel_time_seconds,

        CAST(strftime('%w', arrive_time_utc) AS INTEGER) AS sqlite_dow,  -- 0=Sun..6=Sat
        CAST(strftime('%H', arrive_time_utc) AS INTEGER) AS hour_of_day
    FROM segments
    WHERE travel_time_seconds IS NOT NULL;
    """)

    # Convert sqlite_dow (0=Sun) to 0=Mon..6=Sun
    conn.execute("""
    ALTER TABLE segments_work ADD COLUMN day_of_week INTEGER;
    """)
    conn.execute("""
    UPDATE segments_work
    SET day_of_week = CASE
        WHEN sqlite_dow = 0 THEN 6
        ELSE sqlite_dow - 1
    END;
    """)

    conn.execute("""
    ALTER TABLE segments_work ADD COLUMN time_bucket TEXT;
    """)
    conn.execute("""
    UPDATE segments_work
    SET time_bucket =
        CASE day_of_week
            WHEN 0 THEN 'Mon'
            WHEN 1 THEN 'Tue'
            WHEN 2 THEN 'Wed'
            WHEN 3 THEN 'Thu'
            WHEN 4 THEN 'Fri'
            WHEN 5 THEN 'Sat'
            WHEN 6 THEN 'Sun'
        END || '-' || printf('%02d', hour_of_day);
    """)

    # 1) hard bounds filter (removes obvious glitches)
    conn.execute("DROP TABLE IF EXISTS segments_work2;")
    conn.execute(f"""
    CREATE TEMP TABLE segments_work2 AS
    SELECT *
    FROM segments_work
    WHERE travel_time_seconds BETWEEN {MIN_SECONDS} AND {MAX_SECONDS};
    """)

    # 2) Compute median and MAD per key
    # SQLite doesn't have MEDIAN built-in, so we do a deterministic median using ordered subqueries.
    # We compute:
    # - median (50th percentile)
    # - p10, p90 (approx using rank)
    # - MAD = median(|x - median|)
    conn.execute("DELETE FROM segment_stats;")

    conn.execute("""
    INSERT OR REPLACE INTO segment_stats (
        route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, time_bucket,
        sample_count, median_seconds, mad_seconds, p10_seconds, p90_seconds
    )
    WITH
    base AS (
        SELECT
            route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, time_bucket,
            travel_time_seconds AS x
        FROM segments_work2
    ),
    counts AS (
        SELECT
            route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, time_bucket,
            COUNT(*) AS n
        FROM base
        GROUP BY route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day
    ),
    ranked AS (
        SELECT
            b.*,
            c.n,
            ROW_NUMBER() OVER (
                PARTITION BY b.route_id, b.direction_id, b.from_stop_id, b.to_stop_id, b.day_of_week, b.hour_of_day
                ORDER BY b.x
            ) AS rn
        FROM base b
        JOIN counts c USING (route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, time_bucket)
    ),
    med AS (
        SELECT
            route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, time_bucket,
            n,
            AVG(x) AS median_seconds
        FROM ranked
        WHERE rn IN ((n + 1) / 2, (n + 2) / 2)   -- handles even/odd
        GROUP BY route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day
    ),
    pcts AS (
        SELECT
            route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, time_bucket,
            MAX(CASE WHEN rn = CAST(CEIL(n * 0.10) AS INTEGER) THEN x END) AS p10_seconds,
            MAX(CASE WHEN rn = CAST(CEIL(n * 0.90) AS INTEGER) THEN x END) AS p90_seconds
        FROM ranked
        GROUP BY route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day
    ),
    absdev AS (
        SELECT
            r.route_id, r.direction_id, r.from_stop_id, r.to_stop_id, r.day_of_week, r.hour_of_day, r.time_bucket,
            r.n,
            ABS(r.x - m.median_seconds) AS d
        FROM ranked r
        JOIN med m USING (route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, time_bucket)
    ),
    absrank AS (
        SELECT
            a.*,
            ROW_NUMBER() OVER (
                PARTITION BY a.route_id, a.direction_id, a.from_stop_id, a.to_stop_id, a.day_of_week, a.hour_of_day
                ORDER BY a.d
            ) AS drn
        FROM absdev a
    ),
    mad AS (
        SELECT
            route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, time_bucket,
            AVG(d) AS mad_seconds
        FROM absrank
        WHERE drn IN ((n + 1) / 2, (n + 2) / 2)
        GROUP BY route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day
    )
    SELECT
        c.route_id, c.direction_id, c.from_stop_id, c.to_stop_id, c.day_of_week, c.hour_of_day, c.time_bucket,
        c.n AS sample_count,
        m.median_seconds,
        mad.mad_seconds,
        p.p10_seconds,
        p.p90_seconds
    FROM counts c
    JOIN med m USING (route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, time_bucket)
    LEFT JOIN mad USING (route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, time_bucket)
    LEFT JOIN pcts p USING (route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, time_bucket);
    """)

    # 3) Build segments_clean by joining stats and marking outliers using modified z-score with MAD
    # modified_z = 0.6745 * (x - median) / MAD
    # If MAD == 0 (all identical), we never mark outliers from MAD; only hard bounds already applied.
    conn.execute("DELETE FROM segments_clean;")

    conn.execute(f"""
    INSERT INTO segments_clean (
        id, route_id, direction_id, vehicle_ref, trip_id,
        from_stop_id, to_stop_id, depart_time_utc, arrive_time_utc, travel_time_seconds,
        day_of_week, hour_of_day, time_bucket,
        is_outlier
    )
    SELECT
        w.id, w.route_id, w.direction_id, w.vehicle_ref, w.trip_id,
        w.from_stop_id, w.to_stop_id, w.depart_time_utc, w.arrive_time_utc, w.travel_time_seconds,
        w.day_of_week, w.hour_of_day, w.time_bucket,
        CASE
            WHEN s.mad_seconds IS NULL OR s.mad_seconds = 0 THEN 0
            WHEN ABS(0.6745 * (w.travel_time_seconds - s.median_seconds) / s.mad_seconds) > {MAD_Z_CUTOFF} THEN 1
            ELSE 0
        END AS is_outlier
    FROM segments_work2 w
    JOIN segment_stats s
      ON s.route_id = w.route_id
     AND s.direction_id = w.direction_id
     AND s.from_stop_id = w.from_stop_id
     AND s.to_stop_id = w.to_stop_id
     AND s.day_of_week = w.day_of_week
     AND s.hour_of_day = w.hour_of_day;
    """)

    conn.commit()


def print_coverage_reports(conn: sqlite3.Connection):
    # How many raw vs clean
    raw_n = conn.execute("SELECT COUNT(*) FROM segments;").fetchone()[0]
    clean_n = conn.execute("SELECT COUNT(*) FROM segments_clean WHERE is_outlier = 0;").fetchone()[0]
    out_n = conn.execute("SELECT COUNT(*) FROM segments_clean WHERE is_outlier = 1;").fetchone()[0]

    logging.info(f"Raw segments: {raw_n:,}")
    logging.info(f"Clean kept (non-outliers): {clean_n:,}")
    logging.info(f"Outliers flagged: {out_n:,}")

    # Routes coverage (top 15 by kept samples)
    logging.info("Top routes by clean samples (kept):")
    rows = conn.execute("""
        SELECT route_id, COUNT(*) AS n
        FROM segments_clean
        WHERE is_outlier = 0
        GROUP BY route_id
        ORDER BY n DESC
        LIMIT 15;
    """).fetchall()
    for r in rows:
        logging.info(f"  {r[0]}: {r[1]:,}")

    # Segments with low samples (potential coverage gaps)
    logging.info("Low-coverage stop-pairs (sample_count < 5) in segment_stats (top 20):")
    low = conn.execute("""
        SELECT route_id, direction_id, from_stop_id, to_stop_id, day_of_week, hour_of_day, sample_count
        FROM segment_stats
        WHERE sample_count < 5
        ORDER BY sample_count ASC
        LIMIT 20;
    """).fetchall()
    for r in low:
        logging.info(f"  {r[0]} dir={r[1]} {r[2]}->{r[3]} dow={r[4]} hour={r[5]} n={r[6]}")

    # How many unique stop-pairs we have overall
    uniq_pairs = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT route_id, direction_id, from_stop_id, to_stop_id
            FROM segments_clean
            WHERE is_outlier = 0
        );
    """).fetchone()[0]
    logging.info(f"Unique (route,dir,from,to) pairs in clean data: {uniq_pairs:,}")


def main():
    logging.info("PHASE 5: Organize & Clean starting...")
    logging.info(f"DB: {DB_PATH}")
    logging.info(f"Hard bounds: {MIN_SECONDS}s..{MAX_SECONDS}s")
    logging.info(f"MAD z cutoff: {MAD_Z_CUTOFF}")

    conn = connect()
    init_phase5_tables(conn)
    build_clean_and_stats(conn)
    print_coverage_reports(conn)

    logging.info("PHASE 5 complete. You can now query segments_clean and segment_stats.")


if __name__ == "__main__":
    main()
