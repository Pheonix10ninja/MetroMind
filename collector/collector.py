import os
import time
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import requests

"""
MetroMind Collector (Fixed)

What it does:
- Runs continuously.
- Polls MTA BusTime SIRI Vehicle Monitoring.
- Tracks each bus (VehicleRef) across polls.
- Detects stop-to-stop movement using MonitoredCall.StopPointRef.
- When the next stop changes, records a segment: from_stop -> to_stop with travel time.
- Writes every valid segment immediately to SQLite (no prediction/analysis).
- Handles missing/bad data by skipping safely and continuing.

Storage:
- SQLite DB file at METROMIND_DB (default: /workspaces/MetroMind/metromind_memory.sqlite)
- Table vehicle_state: per-bus last seen next stop + first-seen time
- Table segments: stop-to-stop travel time records

IMPORTANT:
- Set MTA_API_KEY in your environment (Codespaces secret recommended).
- Strongly recommended: set LINE_REF to a single route (e.g. "MTA NYCT_M5") while developing.
"""

# ----------------------------
# CONFIG
# ----------------------------
API_KEY = os.getenv("MTA_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "MTA_API_KEY is not set. Add it as a Codespaces secret or export it in the terminal."
    )

BASE_URL = "https://bustime.mta.info/api/siri/vehicle-monitoring.json"

# Polling interval (seconds)
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))

# Recommended: filter to a single route to reduce load/timeouts.
# Examples: "MTA NYCT_M5", "MTA NYCT_M104", "MTA NYCT_B63"
LINE_REF = os.getenv("LINE_REF")
DIRECTION_REF = os.getenv("DIRECTION_REF")  # optional "0" or "1"

# Use SIRI v2 and NORMAL detail level so MonitoredCall fields are more likely present.
SIRI_VERSION = "2"
DETAIL_LEVEL = os.getenv("DETAIL_LEVEL", "normal")  # default to normal

# Request timeout (seconds) — larger payloads need longer timeout.
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))

# SQLite DB file
DB_PATH = os.getenv("METROMIND_DB", "/workspaces/MetroMind/metromind_memory.sqlite")

# Sanity bounds for segment duration (seconds)
MIN_SEGMENT_SECONDS = int(os.getenv("MIN_SEGMENT_SECONDS", "10"))
MAX_SEGMENT_SECONDS = int(os.getenv("MAX_SEGMENT_SECONDS", "3600"))

# Debug (set DEBUG_SAMPLE=1 to print sample keys once per run)
DEBUG_SAMPLE = os.getenv("DEBUG_SAMPLE", "0") == "1"


# ----------------------------
# LOGGING
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ----------------------------
# HELPERS
# ----------------------------
def unwrap(v: Any) -> Optional[Any]:
    """Normalize fields that may appear as {'value': '...'} or similar."""
    if v is None:
        return None
    if isinstance(v, dict):
        if "value" in v:
            return v["value"]
        if len(v) == 1:
            return next(iter(v.values()))
        return None
    return v


def parse_iso8601(ts: Any) -> Optional[datetime]:
    """Parse ISO8601 timestamps safely."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------
# DB
# ----------------------------
def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def db_init(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id TEXT,
            direction_id TEXT,
            vehicle_ref TEXT,
            trip_id TEXT,
            from_stop_id TEXT NOT NULL,
            to_stop_id TEXT NOT NULL,
            depart_time_utc TEXT NOT NULL,
            arrive_time_utc TEXT NOT NULL,
            travel_time_seconds INTEGER NOT NULL,
            recorded_at_utc TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vehicle_state (
            vehicle_ref TEXT PRIMARY KEY,
            route_id TEXT,
            direction_id TEXT,
            trip_id TEXT,
            current_stop_id TEXT,
            current_stop_first_seen_utc TEXT
        )
        """
    )
    conn.commit()


def load_vehicle_state(conn: sqlite3.Connection, vehicle_ref: str) -> Optional[Dict[str, str]]:
    row = conn.execute(
        "SELECT vehicle_ref, route_id, direction_id, trip_id, current_stop_id, current_stop_first_seen_utc "
        "FROM vehicle_state WHERE vehicle_ref = ?",
        (vehicle_ref,),
    ).fetchone()
    if not row:
        return None
    return {
        "vehicle_ref": row[0],
        "route_id": row[1] or "",
        "direction_id": row[2] or "",
        "trip_id": row[3] or "",
        "current_stop_id": row[4] or "",
        "current_stop_first_seen_utc": row[5] or "",
    }


def upsert_vehicle_state(
    conn: sqlite3.Connection,
    vehicle_ref: str,
    route_id: str,
    direction_id: str,
    trip_id: str,
    stop_id: str,
    first_seen_utc: str,
) -> None:
    conn.execute(
        """
        INSERT INTO vehicle_state (
            vehicle_ref, route_id, direction_id, trip_id, current_stop_id, current_stop_first_seen_utc
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(vehicle_ref) DO UPDATE SET
            route_id=excluded.route_id,
            direction_id=excluded.direction_id,
            trip_id=excluded.trip_id,
            current_stop_id=excluded.current_stop_id,
            current_stop_first_seen_utc=excluded.current_stop_first_seen_utc
        """,
        (vehicle_ref, route_id, direction_id, trip_id, stop_id, first_seen_utc),
    )


def insert_segment(
    conn: sqlite3.Connection,
    route_id: str,
    direction_id: str,
    vehicle_ref: str,
    trip_id: str,
    from_stop: str,
    to_stop: str,
    depart_utc: str,
    arrive_utc: str,
    travel_seconds: int,
) -> None:
    conn.execute(
        """
        INSERT INTO segments (
            route_id, direction_id, vehicle_ref, trip_id,
            from_stop_id, to_stop_id,
            depart_time_utc, arrive_time_utc,
            travel_time_seconds, recorded_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            route_id,
            direction_id,
            vehicle_ref,
            trip_id,
            from_stop,
            to_stop,
            depart_utc,
            arrive_utc,
            int(travel_seconds),
            now_utc_iso(),
        ),
    )


# ----------------------------
# API
# ----------------------------
def fetch_vehicle_monitoring() -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "key": API_KEY,
        "version": SIRI_VERSION,
        "VehicleMonitoringDetailLevel": DETAIL_LEVEL,
    }
    if LINE_REF:
        params["LineRef"] = LINE_REF
    if DIRECTION_REF:
        params["DirectionRef"] = DIRECTION_REF

    r = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


# ----------------------------
# EXTRACTION
# ----------------------------
def extract_vehicle_activities(payload: Dict[str, Any]) -> list:
    """Handle VehicleMonitoringDelivery being a dict or a list."""
    try:
        deliveries = (
            payload.get("Siri", {})
            .get("ServiceDelivery", {})
            .get("VehicleMonitoringDelivery")
        )

        # VehicleMonitoringDelivery may be list or dict
        if isinstance(deliveries, list):
            if not deliveries:
                return []
            deliveries = deliveries[0]

        if isinstance(deliveries, dict):
            acts = deliveries.get("VehicleActivity", [])
            return acts if isinstance(acts, list) else []

        return []
    except Exception:
        return []


def extract_fields(activity: Dict[str, Any]) -> Optional[Tuple[str, str, str, str, str, datetime]]:
    """Return (vehicle_ref, route_id, direction_id, trip_id, next_stop_id, recorded_at_dt) or None."""
    recorded_at = parse_iso8601(activity.get("RecordedAtTime"))
    mvj = activity.get("MonitoredVehicleJourney") or {}

    vehicle_ref = unwrap(mvj.get("VehicleRef"))
    route_id = unwrap(mvj.get("LineRef")) or unwrap(mvj.get("PublishedLineName")) or ""

    direction_id_val = unwrap(mvj.get("DirectionRef"))
    direction_id = str(direction_id_val) if direction_id_val is not None else ""

    fref = mvj.get("FramedVehicleJourneyRef") or {}
    trip_id = unwrap(fref.get("DatedVehicleJourneyRef")) or ""

    monitored_call = mvj.get("MonitoredCall") or {}
    next_stop_id = unwrap(monitored_call.get("StopPointRef"))

    # Required for stop-to-stop tracking
    if not recorded_at or not vehicle_ref or not next_stop_id:
        return None

    return (str(vehicle_ref), str(route_id), str(direction_id), str(trip_id), str(next_stop_id), recorded_at)


# ----------------------------
# CORE LOGIC
# ----------------------------
def handle_observation(conn: sqlite3.Connection, obs: Tuple[str, str, str, str, str, datetime]) -> None:
    vehicle_ref, route_id, direction_id, trip_id, next_stop_id, recorded_at_dt = obs
    recorded_at_utc = utc_iso(recorded_at_dt)

    prev = load_vehicle_state(conn, vehicle_ref)

    # First time seeing this bus
    if prev is None or not prev.get("current_stop_id"):
        upsert_vehicle_state(conn, vehicle_ref, route_id, direction_id, trip_id, next_stop_id, recorded_at_utc)
        return

    prev_stop = prev["current_stop_id"]
    prev_first_seen_dt = parse_iso8601(prev["current_stop_first_seen_utc"])

    # If stop hasn't changed, just refresh metadata
    if next_stop_id == prev_stop:
        upsert_vehicle_state(conn, vehicle_ref, route_id, direction_id, trip_id, prev_stop, prev["current_stop_first_seen_utc"])
        return

    # Stop changed: treat as completion of segment prev_stop -> next_stop_id
    if not prev_first_seen_dt:
        # Broken state; reset safely
        upsert_vehicle_state(conn, vehicle_ref, route_id, direction_id, trip_id, next_stop_id, recorded_at_utc)
        return

    travel_seconds = int((recorded_at_dt - prev_first_seen_dt).total_seconds())

    # Sanity checks
    if travel_seconds < MIN_SEGMENT_SECONDS or travel_seconds > MAX_SEGMENT_SECONDS:
        upsert_vehicle_state(conn, vehicle_ref, route_id, direction_id, trip_id, next_stop_id, recorded_at_utc)
        return

    # Save immediately (no prediction)
    insert_segment(
        conn=conn,
        route_id=prev.get("route_id", route_id) or route_id,
        direction_id=prev.get("direction_id", direction_id) or direction_id,
        vehicle_ref=vehicle_ref,
        trip_id=prev.get("trip_id", trip_id) or trip_id,
        from_stop=prev_stop,
        to_stop=next_stop_id,
        depart_utc=prev["current_stop_first_seen_utc"],
        arrive_utc=recorded_at_utc,
        travel_seconds=travel_seconds,
    )

    # Update state to new next stop
    upsert_vehicle_state(conn, vehicle_ref, route_id, direction_id, trip_id, next_stop_id, recorded_at_utc)


# ----------------------------
# MAIN LOOP
# ----------------------------
def main() -> None:
    logging.info("MetroMind collector starting...")
    logging.info(f"DB: {DB_PATH}")
    logging.info(f"Poll interval: {POLL_SECONDS}s")
    logging.info(f"DETAIL_LEVEL: {DETAIL_LEVEL}")

    if LINE_REF:
        logging.info(f"Filtering LineRef: {LINE_REF}")
    else:
        logging.warning("No LineRef filter set. This may be heavy. Consider setting LINE_REF env var.")

    conn = db_connect()
    db_init(conn)

    sample_logged = False

    while True:
        try:
            payload = fetch_vehicle_monitoring()
            activities = extract_vehicle_activities(payload)

            # Optional debug: print sample structure once
            if DEBUG_SAMPLE and activities and not sample_logged:
                sample = activities[0]
                mvj = sample.get("MonitoredVehicleJourney", {})
                logging.info(f"Sample VehicleActivity keys: {list(sample.keys())}")
                logging.info(f"Sample MVJ keys: {list(mvj.keys())}")
                logging.info(f"Sample MonitoredCall: {mvj.get('MonitoredCall')}")
                sample_logged = True

            processed = 0
            skipped = 0

            for act in activities:
                obs = extract_fields(act)
                if obs is None:
                    skipped += 1
                    continue
                try:
                    handle_observation(conn, obs)
                    processed += 1
                except Exception:
                    skipped += 1
                    continue

            conn.commit()
            logging.info(f"Tick: processed={processed}, skipped={skipped}, vehicles_seen={len(activities)}")

        except requests.RequestException as e:
            logging.error(f"Network/API error: {e}")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Stopped by user (Ctrl+C).")
