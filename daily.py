from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import csv
from collections import defaultdict

# ---- CONFIG ----
FILE = "export.xml"  # Your Apple Health export file
START = datetime(2023, 1, 1, tzinfo=timezone.utc)
END   = datetime(2023, 12, 31, tzinfo=timezone.utc)
OUTPUT_CSV = "daily_totals.csv"
# ----------------

tree = ET.parse(FILE)
root = tree.getroot()

# Dictionary to store totals per day
daily_data = defaultdict(lambda: {"steps": 0, "distance": 0, "calories": 0})

for record in root.findall(".//Record"):
    dtype = record.attrib.get("type")
    startDate = record.attrib.get("startDate")

    try:
        dt = datetime.fromisoformat(startDate.replace(" +", "+"))
    except Exception:
        continue  # skip malformed dates

    if START <= dt <= END:
        value_str = record.attrib.get("value", "0")
        try:
            value = float(value_str)
        except ValueError:
            continue  # skip non-numeric values

        day_key = dt.date()  # group by day

        if dtype == "HKQuantityTypeIdentifierStepCount":
            daily_data[day_key]["steps"] += value
        elif dtype == "HKQuantityTypeIdentifierDistanceWalkingRunning":
            daily_data[day_key]["distance"] += value  # already in km
        elif dtype == "HKQuantityTypeIdentifierActiveEnergyBurned":
            daily_data[day_key]["calories"] += value

# ---- WRITE CSV ----
with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Date", "Steps", "Distance (km)", "Active Calories (kcal)"])
    for day in sorted(daily_data.keys()):
        data = daily_data[day]
        writer.writerow([
            day,
            f"{data['steps']:.0f}",
            f"{data['distance']:.2f}",
            f"{data['calories']:.2f}"
        ])

print(f"Daily totals exported to '{OUTPUT_CSV}'")
