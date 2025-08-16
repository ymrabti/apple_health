import xml.etree.ElementTree as ET
from datetime import datetime,timezone

# Path to export.xml
tree = ET.parse('export.xml')
root = tree.getroot()

# Period to sum
start = datetime(2025, 6, 30, tzinfo=timezone.utc)
end   = datetime(2025, 8, 15, tzinfo=timezone.utc)

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
            if record.attrib['unit']=='km':
                print(record.attrib)
            types[rtype] += float(record.attrib['value'])

print("Steps:", types['HKQuantityTypeIdentifierStepCount'])
print("Distance (km):", types['HKQuantityTypeIdentifierDistanceWalkingRunning'])
print("Active Calories (kcal):", types['HKQuantityTypeIdentifierActiveEnergyBurned'])
