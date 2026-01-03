"""
Docker worker that watches for new Apple Health XML files and processes them.
Monitors a shared volume for job files created by the Node.js backend.
"""

import os
import time
import json
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict
import urllib.request as urlrequest
import urllib.error as urlerror
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Environment configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:7384")
FOLDER = "../apple_health_webservice"
WATCH_DIR = Path(
    os.getenv(
        "WATCH_DIR",
        f"{FOLDER}/static",
    )
)
PROCESSED_DIR = Path(
    os.getenv(
        "PROCESSED_DIR",
        f"{FOLDER}/static/processed",
    )
)

# Ensure directories exist
WATCH_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


class HealthDataProcessor:
    """Process Apple Health XML files and post to backend."""

    def __init__(self, backend_url: str):
        self.backend_url = backend_url

    def _post_json(self, endpoint: str, payload: dict, token: str) -> bool:
        """Post JSON data to backend with JWT token."""
        try:
            url = f"{self.backend_url}{endpoint}"
            data = json.dumps(payload).encode("utf-8")
            req = urlrequest.Request(
                url,
                data=data,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )
            with urlrequest.urlopen(req, timeout=30) as resp:
                status = resp.status
                print(f"✅ POST {endpoint} → {status}")
                return 200 <= status < 300
        except urlerror.HTTPError as e:
            print(f"❌ POST {endpoint} failed: HTTP {e.code} - {e.reason}")
            return False
        except urlerror.URLError as e:
            print(f"❌ POST {endpoint} failed: {e.reason}")
            return False
        except (ValueError, TypeError, OSError) as e:
            print(f"❌ POST {endpoint} failed: {e}")
            return False

    def _post_in_batches(
        self,
        endpoint: str,
        items: list,
        token: str,
        chunk_size: int = 100,
        export_date: str = None,
    ) -> bool:
        """Post data in batches to avoid payload size limits."""
        if not items:
            print(f"⚠️  No items to post to {endpoint}")
            return True

        total = len(items)
        print(f"📦 Posting {total} items to {endpoint} in batches of {chunk_size}")

        for start in range(0, total, chunk_size):
            end = min(start + chunk_size, total)
            chunk = items[start:end]

            if "daily-summaries" in endpoint:
                payload = {"summaries": chunk}
            elif "activity-summaries" in endpoint:
                payload = {"summaries": chunk}
                if export_date:
                    payload["exportDate"] = export_date
            else:
                payload = {"items": chunk}

            ok = self._post_json(endpoint, payload, token)
            if not ok:
                print(f"❌ Failed to post batch {start}-{end}/{total}")
                return False
            print(f"✅ Posted batch {start+1}-{end}/{total}")
            time.sleep(0.1)  # Small delay between batches

        return True

    def process_xml(self, xml_path: Path, token: str) -> bool:
        """Process Apple Health XML and post to backend."""
        try:
            print(f"\n{'='*60}")
            print(f"📝 Processing {xml_path.name}...")
            print(f"{'='*60}")

            tree = ET.parse(xml_path)
            root = tree.getroot()

            # Extract metadata
            me_elem = root.find(".//Me")
            me_attrs = me_elem.attrib if me_elem is not None else {}
            weight = root.find(".//Record[@type='HKQuantityTypeIdentifierBodyMass']")
            height = root.find(".//Record[@type='HKQuantityTypeIdentifierHeight']")
            if weight is not None:
                me_attrs["weightInKilograms"] = weight.attrib.get("value")
            if height is not None:
                me_attrs["heightInCentimeters"] = height.attrib.get("value")

            # Extract export date
            export_date = self._get_export_date(root)
            print(f"📅 Export Date: {export_date}")

            # Aggregate daily data
            print("🔄 Aggregating daily data...")
            daily_data = self._aggregate_daily(root)
            print(f"📊 Found {len(daily_data)} days of data")

            # Post user info
            print("\n👤 Posting user info...")
            user_payload = {"exportDate": export_date, "attributes": me_attrs}
            self._post_json("/api/apple-health/user-infos", user_payload, token)

            # Post daily summaries
            print("\n📈 Posting daily summaries...")
            summaries = self._build_summaries(daily_data, export_date)
            self._post_in_batches("/api/apple-health/daily-summaries", summaries, token)

            # Post activity summaries
            print("\n🏃 Posting activity summaries...")
            activity_summaries = [
                dict(rec.attrib) for rec in root.findall(".//ActivitySummary")
            ]
            if activity_summaries:
                self._post_in_batches(
                    "/api/apple-health/activity-summaries",
                    activity_summaries,
                    token,
                    export_date=export_date,
                )
            else:
                print("⚠️  No activity summaries found")

            print("\n" + "=" * 60)
            print("✅ Successfully processed " + xml_path.name)
            print("=" * 60 + "\n")
            return True

        except ET.ParseError as e:
            print(f"❌ XML Parse Error in {xml_path.name}: {e}")
            return False
        except (OSError, IOError, AttributeError, KeyError, ValueError) as e:
            print(f"❌ Error processing {xml_path.name}: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _get_export_date(self, root) -> str:
        """Extract export date from XML."""
        try:
            elem = root.find(".//ExportDate")
            if elem is None:
                return datetime.now().strftime("%Y-%m-%d")

            val = elem.attrib.get("value") or elem.attrib.get("date") or elem.text
            if val and "T" in val:
                val = val.split("T")[0]
            return val[:10] if val else datetime.now().strftime("%Y-%m-%d")
        except (AttributeError, KeyError, TypeError):
            return datetime.now().strftime("%Y-%m-%d")

    def _aggregate_daily(self, root):
        """Aggregate health records by day."""
        aggregate_map = {
            "HKQuantityTypeIdentifierStepCount": "steps",
            "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance",
            "HKQuantityTypeIdentifierActiveEnergyBurned": "calories",
            "HKQuantityTypeIdentifierBasalEnergyBurned": "basal_calories",
            "HKQuantityTypeIdentifierFlightsClimbed": "flights",
            "HKQuantityTypeIdentifierAppleExerciseTime": "exercise",
        }

        daily_data = defaultdict(lambda: {k: 0 for k in aggregate_map.values()})

        for record in root.findall(".//Record"):
            dtype = record.attrib.get("type")
            if dtype not in aggregate_map:
                continue

            try:
                startdate = record.attrib.get("startDate")
                dt = datetime.fromisoformat(startdate.replace(" +", "+"))
                value = float(record.attrib.get("value", "0"))

                day_key = dt.date()
                key = aggregate_map[dtype]
                daily_data[day_key][key] += value
            except (ValueError, TypeError):
                continue

        return daily_data

    def _build_summaries(self, daily_data, export_date):
        """Build summary objects for API."""
        summaries = []
        for day, metrics in sorted(daily_data.items()):
            item = {
                "date": day.isoformat(),
                "steps": int(round(metrics.get("steps", 0))),
                "flights": int(round(metrics.get("flights", 0))),
                "distance": round(metrics.get("distance", 0), 4),
                "active": round(metrics.get("calories", 0), 4),
                "basal": round(metrics.get("basal_calories", 0), 4),
                "exercise": round(metrics.get("exercise", 0), 4),
                "exportDate": export_date,
            }
            summaries.append(item)
        return summaries


class HealthFileHandler(FileSystemEventHandler):
    """Watch for new XML/JSON job files and process them."""

    def __init__(self, processor: HealthDataProcessor):
        self.processor = processor
        self.processing = set()

    def on_created(self, event):
        """Handle new file creation."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Look for job metadata JSON files
        if file_path.suffix == ".json" and file_path.stem.endswith("_job"):
            # Small delay to ensure file is fully written
            time.sleep(0.5)
            self._process_job(file_path)

    def _process_job(self, job_file: Path):
        """Process a job file containing XML path and token."""
        if str(job_file) in self.processing:
            return

        self.processing.add(str(job_file))

        try:
            # Read job metadata
            with open(job_file, "r", encoding="utf-8") as f:
                job = json.load(f)

            xml_path = Path(job["xml_path"])
            token = job["token"]
            user_id = job.get("user_id", "unknown")

            if not xml_path.exists():
                print(f"❌ XML file not found: {xml_path}")
                return

            print(f"\n🚀 Starting job for user {user_id}")
            print(f"📄 File: {xml_path.name}")

            # Process the XML
            success = self.processor.process_xml(xml_path, token)

            if success:
                # Move to processed directory
                user_processed_dir = PROCESSED_DIR / user_id
                user_processed_dir.mkdir(parents=True, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                processed_xml = user_processed_dir / f"{timestamp}_export.xml"
                shutil.move(str(xml_path), str(processed_xml))

                # Delete job file
                job_file.unlink()
                print(f"✅ Job completed and archived: {processed_xml}")
            else:
                print(f"❌ Job failed for {xml_path.name}")

        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in job file {job_file}: {e}")
        except (OSError, IOError, KeyError, ValueError, FileNotFoundError) as e:
            print(f"❌ Error processing job {job_file}: {e}")
            import traceback

            traceback.print_exc()
        finally:
            self.processing.discard(str(job_file))


def main():
    """Start the file watcher worker."""
    print("\n" + "=" * 60)
    print("🏥 Apple Health Data Worker")
    print("=" * 60)
    print(f"📍 Backend: {BACKEND_URL}")
    print(f"📂 Watch dir: {WATCH_DIR}")
    print(f"📂 Processed dir: {PROCESSED_DIR}")
    print("=" * 60 + "\n")

    processor = HealthDataProcessor(BACKEND_URL)
    handler = HealthFileHandler(processor)

    observer = Observer()
    observer.schedule(handler, str(WATCH_DIR), recursive=True)
    observer.start()

    print("✅ Worker ready. Watching for new health data...\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n🛑 Worker stopped.")

    observer.join()


if __name__ == "__main__":
    main()
