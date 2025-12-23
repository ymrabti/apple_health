"""
Apply daily aggregation and export to Excel file with three sheets:
1. Daily totals (Steps, Distance, Active Calories)
2. Weekly totals (Steps, Distance, Active Calories)
3. Daily statistics summary (Sum, Max, Min, Median, Average for each metric)
4. Date range of the data
"""

import sys
import statistics
from datetime import datetime, timezone, time, timedelta
import xml.etree.ElementTree as ET
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse as urlparse
import threading
import webbrowser
import signal
import time as systime
from openpyxl import Workbook
import keyring

APP_NAME = "health_dashboard"
SERVER_URL = "http://localhost:3762/oauth/callback"
CRED_KEY = "jwt_token"

# ---- CONFIG ----
FILE = "export.xml"
# ----------------
tree = ET.parse(FILE)
root = tree.getroot()

# Global synchronization primitives for OAuth
AUTH_SUCCESS = threading.Event()
SERVER_READY = threading.Event()
SERVER_INSTANCE = None  # type: HTTPServer | None
LISTEN_PORT = None  # type: int | None
CANCEL_EVENT = threading.Event()


def get_stored_token():
    """Retrieve stored JWT token from keyring."""
    return keyring.get_password(APP_NAME, CRED_KEY)


def store_token(token_back: str):
    """Store JWT token securely in keyring."""
    keyring.set_password(APP_NAME, CRED_KEY, token_back)


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to process OAuth callback and extract JWT token."""

    def do_GET(self):
        """Handle GET request to extract JWT token from query parameters."""
        # extract JWT from query string: ?token=...

        query = urlparse.urlparse(self.path).query
        params = urlparse.parse_qs(query)
        token_oauth = params.get("token", [None])[0]
        if token_oauth:
            store_token(token_oauth)
            # Signal success to the main process
            AUTH_SUCCESS.set()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authentication successful. You can close this window.")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Authentication failed.")


def start_local_server(preferred_port: int = 8765):
    """Start a local HTTP server to handle OAuth callback (until shutdown).
    Tries preferred_port first, falls back to any free port.
    Signals readiness via SERVER_READY and records LISTEN_PORT.
    """
    global SERVER_INSTANCE, LISTEN_PORT
    try:
        httpd = HTTPServer(("127.0.0.1", preferred_port), CallbackHandler)
    except OSError:
        # Fallback to any available port
        httpd = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    SERVER_INSTANCE = httpd
    LISTEN_PORT = httpd.server_address[1]
    SERVER_READY.set()
    # Serve until `shutdown()` is called from the main thread.
    httpd.serve_forever(poll_interval=0.5)


def ensure_authenticated():
    """Ensure the user is authenticated and return the JWT token."""
    token_back = get_stored_token()
    if token_back:
        return token_back

    # launch local server in background (prefer 8765)
    server_thread = threading.Thread(
        target=start_local_server, kwargs={"preferred_port": 8765}, daemon=True
    )
    server_thread.start()

    # wait for server readiness to know the actual port
    if not SERVER_READY.wait(timeout=5):
        # could not start server; cancel
        if SERVER_INSTANCE is not None:
            try:
                SERVER_INSTANCE.shutdown()
            except OSError:
                pass
        server_thread.join(timeout=2)
        print("❌ Failed to start local callback server.")
        return None

    # open browser to authenticate with the actual chosen port
    redirect_url = f"http://127.0.0.1:{LISTEN_PORT}/callback"
    auth_url = f"{SERVER_URL}?provider={redirect_url}"
    webbrowser.open(auth_url)

    # wait up to 5 minutes for authentication to complete; allow Ctrl+C to cancel
    deadline = systime.monotonic() + 300
    success = False
    try:
        while True:
            if AUTH_SUCCESS.is_set():
                success = True
                break
            if CANCEL_EVENT.is_set():
                raise KeyboardInterrupt
            remaining = deadline - systime.monotonic()
            if remaining <= 0:
                success = False
                break
            # poll in small intervals to allow signal handling
            AUTH_SUCCESS.wait(timeout=min(0.25, remaining))
    finally:
        # stop the local server regardless of outcome
        if SERVER_INSTANCE is not None:
            try:
                SERVER_INSTANCE.shutdown()
            except Exception:
                pass
        server_thread.join(timeout=2)

    if not success:
        # Timed out or interrupted: cancel process
        return None

    return get_stored_token()


def parse_apple_health(start_dt, end_dt):
    """Parse Apple Health XML export and return daily summaries."""
    # Dummy implementation – replace with your parser
    date = start_dt
    data = []
    while date <= end_dt:
        data.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "steps": 10000,
                "distance": 7.2,
                "calories": 2100,
            }
        )
        date += timedelta(days=1)
    return data


def format_number(value, width=10):
    """
    Format a number with:
    - Thousand separator (.)
    - Decimal comma (,)
    - Left-padded with spaces to a total width
    """
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return formatted.rjust(width, " ")


def export_excel(_start, _end):
    """Export daily and weekly aggregated data to an Excel file."""
    # ---- Aggregate daily data ----
    # ---- Aggregate daily data ----
    daily_data = defaultdict(
        lambda: {"steps": 0, "distance": 0, "calories": 0, "flights": 0, "exercise": 0}
    )

    # ---- Aggregate weekly data ----
    weekly_data = defaultdict(
        lambda: {"steps": 0, "distance": 0, "calories": 0, "flights": 0, "exercise": 0}
    )

    for record in root.findall(".//ActivitySummary"):
        print(record.attrib)
    for record in root.findall(".//Record"):
        dtype = record.attrib.get("type")

        try:
            start_date = record.attrib.get("startDate")
            dt = datetime.fromisoformat(start_date.replace(" +", "+"))
        except ValueError:
            continue

        if _start <= dt <= _end:
            value_str = record.attrib.get("value", "0")
            try:
                value = float(value_str)
            except ValueError:
                continue

            day_key = dt.date()
            if dtype == "HKQuantityTypeIdentifierStepCount":
                daily_data[day_key]["steps"] += value
            elif dtype == "HKQuantityTypeIdentifierDistanceWalkingRunning":
                daily_data[day_key]["distance"] += value
            elif dtype == "HKQuantityTypeIdentifierActiveEnergyBurned":
                daily_data[day_key]["calories"] += value
            elif dtype == "HKQuantityTypeIdentifierFlightsClimbed":
                daily_data[day_key]["flights"] += value
            elif dtype == "HKQuantityTypeIdentifierAppleExerciseTime":
                daily_data[day_key]["exercise"] += value

    for day, data in daily_data.items():
        year, week, _ = day.isocalendar()
        week_key = f"{year}-W{week:02d}"
        weekly_data[week_key]["steps"] += data["steps"]
        weekly_data[week_key]["distance"] += data["distance"]
        weekly_data[week_key]["calories"] += data["calories"]
        weekly_data[week_key]["flights"] += data["flights"]
        weekly_data[week_key]["exercise"] += data["exercise"]

    # ---- Create Excel file ----
    wb = Workbook()

    # --- Daily Sheet ---
    daily_sheet = wb.active
    daily_sheet.title = "Daily Totals"
    daily_sheet.append(
        [
            "Date",
            "Steps",
            "Distance (km)",
            "Active Calories (kcal)",
            "Flights",
            "Exercise(minutes)",
        ]
    )
    for day in sorted(daily_data.keys()):
        data = daily_data[day]
        daily_sheet.append(
            [
                day.isoformat(),
                int(data["steps"]),
                format_number(round(data["distance"], 2)),
                int(data["calories"]),
                int(data["flights"]),
                int(data["exercise"]),
            ]
        )

    # --- Weekly Sheet ---
    weekly_sheet = wb.create_sheet(title="Weekly Totals")
    weekly_sheet.append(
        [
            "Week",
            "Steps",
            "Distance (km)",
            "Active Calories (kcal)",
            "Flights",
            "Exercise(minutes)",
        ]
    )
    for week in sorted(weekly_data.keys()):
        data = weekly_data[week]
        weekly_sheet.append(
            [
                week,
                int(data["steps"]),
                format_number(round(data["distance"], 2)),
                int(data["calories"]),
                int(data["flights"]),
                int(data["exercise"]),
            ]
        )

    # --- Daily Statistics Sheet ---
    stats_sheet = wb.create_sheet(title="Daily Stats Summary")
    stats_sheet.append(
        [
            "Metric",
            "Sum",
            "Max",
            "Day Hit Max",
            "Min",
            "Day Hit Min",
            "Median",
            "Average",
        ]
    )

    # Prepare lists and corresponding dates
    steps_list = [data["steps"] for data in daily_data.values()]
    steps_dates = list(daily_data.keys())
    distance_list = [data["distance"] for data in daily_data.values()]
    distance_dates = list(daily_data.keys())
    calories_list = [data["calories"] for data in daily_data.values()]
    flights_list = [data["flights"] for data in daily_data.values()]
    exercise_list = [data["exercise"] for data in daily_data.values()]
    calories_dates = list(daily_data.keys())

    def get_day_of_value(lst, dates, value):
        """Return the first date corresponding to the value"""
        for v, d in zip(lst, dates):
            if v == value:
                return d.isoformat()
        return ""

    metrics = [
        ("Steps", steps_list, steps_dates),
        ("Distance (km)", distance_list, distance_dates),
        ("Active Calories (kcal)", calories_list, calories_dates),
        ("Flights", flights_list, calories_dates),
        ("Exercise(in minutes)", exercise_list, calories_dates),
    ]

    for name, lst, dates in metrics:
        max_val = max(lst)
        min_val = min(lst)
        stats_sheet.append(
            [
                name,
                format_number(round(sum(lst), 2)),
                format_number(round(max_val, 2)),
                get_day_of_value(lst, dates, max_val),
                format_number(round(min_val, 2)),
                get_day_of_value(lst, dates, min_val),
                format_number(round(statistics.median(lst), 2)),
                format_number(round(statistics.mean(lst), 2)),
            ]
        )
    stats_sheet.append(
        [
            "Date Range",
            "Start Date",
            min(daily_data.keys()).isoformat(),
            "End Date",
            max(daily_data.keys()).isoformat(),
        ]
    )
    output_xlsx = f"activity_summaries/{_start.date()}-{_end.date()}.xlsx"
    # ---- Save Excel ----
    wb.save(output_xlsx)
    print(f"Daily, weekly, and daily stats summary exported to '{output_xlsx}'")


# --- 1️⃣ Parse CMD Arguments ---
if len(sys.argv) != 3:
    print("Usage: python daily_stats.py <start_date> <end_date>")
    print("Example: python daily_stats.py 2025-08-01 2025-08-31")
    sys.exit(1)


def _sigint_handler(_signum, _frame):
    CANCEL_EVENT.set()


try:
    # install Ctrl+C handler
    try:
        signal.signal(signal.SIGINT, _sigint_handler)
    except Exception:
        # In some environments signals may not be configurable; ignore
        pass
    start_date = datetime.combine(
        datetime.strptime(sys.argv[1], "%Y-%m-%d").date(), time.min, tzinfo=timezone.utc
    )
    end_date = datetime.combine(
        datetime.strptime(sys.argv[2], "%Y-%m-%d").date(), time.max, tzinfo=timezone.utc
    )

    token = ensure_authenticated()
    if CANCEL_EVENT.is_set():
        print("\nOperation cancelled by user.")
        sys.exit(1)
    if not token:
        print("⚠️ Authentication timed out (5 minutes). Process cancelled.")
        sys.exit(1)
    summaries = parse_apple_health(start_date, end_date)
    export_excel(start_date, end_date)
except ValueError:
    print("❌ Dates must be in YYYY-MM-DD format")
    sys.exit(1)
except KeyboardInterrupt:
    # Ensure server is shut down if running and exit cleanly
    if SERVER_INSTANCE is not None:
        try:
            SERVER_INSTANCE.shutdown()
        except Exception:
            pass
    print("\nOperation cancelled by user.")
    sys.exit(1)
