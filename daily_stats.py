from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
import isoweek

# ---- CONFIG ----
FILE = "export.xml"  # Your Apple Health export file
START = datetime(2025, 6, 23, tzinfo=timezone.utc)
END   = datetime(2025, 8, 15, tzinfo=timezone.utc)
OUTPUT_XLSX = "activity_summary.xlsx"
# ----------------

tree = ET.parse(FILE)
root = tree.getroot()

# ---- Aggregate daily data ----
daily_data = defaultdict(lambda: {"steps": 0, "distance": 0, "calories": 0})

for record in root.findall(".//Record"):
    dtype = record.attrib.get("type")
    startDate = record.attrib.get("startDate")

    try:
        dt = datetime.fromisoformat(startDate.replace(" +", "+"))
    except Exception:
        continue

    if START <= dt <= END:
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
    year, week, _ = day.isocalendar()  # ISO week
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
            round(data["distance"], 2),
            round(data["calories"], 2),
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
            round(data["distance"], 2),
            round(data["calories"], 2),
        ]
    )

# --- Adjust column widths ---
for sheet in [daily_sheet, weekly_sheet]:
    for col in sheet.columns:
        max_length = max(len(str(cell.value)) for cell in col)
        sheet.column_dimensions[get_column_letter(col[0].column)].width = max_length + 2

# ---- Save Excel ----
wb.save(OUTPUT_XLSX)
print(f"Daily and weekly statistics exported to '{OUTPUT_XLSX}'")
