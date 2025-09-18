"""
Apply daily aggregation and export to Excel file with three sheets:
1. Daily totals (Steps, Distance, Active Calories)
2. Weekly totals (Steps, Distance, Active Calories)
3. Daily statistics summary (Sum, Max, Min, Median, Average for each metric)
4. Date range of the data
"""

import sys
import statistics
from datetime import datetime, timezone, time
import xml.etree.ElementTree as ET
from collections import defaultdict
from openpyxl import Workbook

# ---- CONFIG ----
FILE = "export.xml"
# ----------------


tree = ET.parse(FILE)
root = tree.getroot()


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
    daily_data = defaultdict(lambda: {"steps": 0, "distance": 0, "calories": 0})

    for record in root.findall(".//Record"):
        dtype = record.attrib.get("type")

        try:
            record_start_date = record.attrib.get("startDate")
            dt = datetime.fromisoformat(record_start_date.replace(" +", "+"))
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

    # ---- Aggregate weekly data ----
    weekly_data = defaultdict(lambda: {"steps": 0, "distance": 0, "calories": 0})
    for day, data in daily_data.items():
        year, week, _ = day.isocalendar()
        week_key = f"{year}-W{week:02d}"
        weekly_data[week_key]["steps"] += data["steps"]
        weekly_data[week_key]["distance"] += data["distance"]
        weekly_data[week_key]["calories"] += data["calories"]

    # ---- Create Excel file ----
    wb = Workbook()

    # --- Daily Sheet ---
    daily_sheet = wb.active
    daily_sheet.title = "Daily Totals"
    daily_sheet.append(["Date", "Steps", "Distance (km)", "Active Calories (kcal)"])
    for day in sorted(daily_data.keys()):
        data = daily_data[day]
        daily_sheet.append(
            [
                day.isoformat(),
                int(data["steps"]),
                format_number(round(data["distance"], 2)),
                format_number(round(data["calories"], 2)),
            ]
        )

    # --- Weekly Sheet ---
    weekly_sheet = wb.create_sheet(title="Weekly Totals")
    weekly_sheet.append(["Week", "Steps", "Distance (km)", "Active Calories (kcal)"])
    for week in sorted(weekly_data.keys()):
        data = weekly_data[week]
        weekly_sheet.append(
            [
                week,
                int(data["steps"]),
                format_number(round(data["distance"], 2)),
                format_number(round(data["calories"], 2)),
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
    output_xlsx = f"activity_summary_{_start.date()}-{_end.date()}.xlsx"
    # ---- Save Excel ----
    wb.save(output_xlsx)
    print(f"Daily, weekly, and daily stats summary exported to '{output_xlsx}'")


# --- 1️⃣ Parse CMD Arguments ---
if len(sys.argv) != 3:
    print("Usage: python daily_stats.py <start_date> <end_date>")
    print("Example: python daily_stats.py 2025-08-01 2025-08-28")
    sys.exit(1)

try:
    start_date = datetime.combine(
        datetime.strptime(sys.argv[1], "%Y-%m-%d").date(), time.min, tzinfo=timezone.utc
    )
    end_date = datetime.combine(
        datetime.strptime(sys.argv[2], "%Y-%m-%d").date(), time.max, tzinfo=timezone.utc
    )
    export_excel(start_date, end_date)
except ValueError:
    print("❌ Dates must be in YYYY-MM-DD format")
    sys.exit(1)
