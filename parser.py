import xml.etree.ElementTree as ET
from datetime import datetime,timezone

# Path to export.xml
tree = ET.parse('export.xml')
root = tree.getroot()

# Period to sum
start = datetime(2025, 6, 30, tzinfo=timezone.utc)
end   = datetime(2025, 8, 18, tzinfo=timezone.utc)

# Data categories we want
types = {
    'HKQuantityTypeIdentifierStepCount': 0,
    'HKQuantityTypeIdentifierDistanceWalkingRunning': 0,
    'HKQuantityTypeIdentifierActiveEnergyBurned': 0
}

for record in root.findall('Record'):
    rtype = record.attrib['type']
    if rtype in types:
        dt = datetime.fromisoformat(record.attrib['startDate'].replace(' +0100', '+01:00'))
        if start <= dt <= end:
            types[rtype] += float(record.attrib['value'])

print("Steps:", round(types['HKQuantityTypeIdentifierStepCount'], 2))
print("Distance (km):", round(types['HKQuantityTypeIdentifierDistanceWalkingRunning'], 2))
print("Active Calories (kcal):", round(types['HKQuantityTypeIdentifierActiveEnergyBurned'], 2))
