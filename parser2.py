from datetime import datetime, timezone
import xml.etree.ElementTree as ET

# ---- CONFIG ----
FILE = "export.xml"  # your Apple Health export file
START = datetime(2023, 1, 1, tzinfo=timezone.utc)
END   = datetime(2023, 12, 31, tzinfo=timezone.utc)
# ----------------

tree = ET.parse(FILE)
root = tree.getroot()

steps_total = 0
distance_total = 0
calories_total = 0

for record in root.findall(".//Record"):
    dtype = record.attrib.get("type")
    startDate = record.attrib.get("startDate")

    try:
        dt = datetime.fromisoformat(startDate.replace(" +", "+"))
    except Exception:
        continue  # skip malformed dates

    if START <= dt <= END:
        value_str = record.attrib.get("value", "0")

        # Skip non-numeric values (e.g., sleep analysis categories)
        try:
            value = float(value_str)
        except ValueError:
            continue

        if dtype == "HKQuantityTypeIdentifierStepCount":
            steps_total += value
        elif dtype == "HKQuantityTypeIdentifierDistanceWalkingRunning":
            distance_total += value  # already in km
        elif dtype == "HKQuantityTypeIdentifierActiveEnergyBurned":
            calories_total += value

# ---- OUTPUT ----
print(f"Steps: {steps_total:,.0f}")
print(f"Distance: {distance_total:,.2f} km")
print(f"Active Calories: {calories_total:,.2f} kcal")
