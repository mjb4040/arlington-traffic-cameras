"""
Data Stewardship Agent - Step 2: Diff Script
Fetches fresh Arlington traffic camera data and compares it to the
current cleaned JSON, producing a structured diff report.
"""

import json
import requests
from datetime import datetime

# --- Config ---
ARLINGTON_API_URL = "https://datahub-v2-s3.arlingtonva.us/Uploads/AutomatedJobs/Traffic+Cameras.json?$top=10000"
LOCAL_JSON_PATH = "traffic_cameras_clean.json"

# --- Field mapping ---
# Maps Arlington API field names to your cleaned JSON field names
# Update these if the API fields differ after inspection
FIELD_MAP = {
    "Camera EncoderB2": "camera_name",
    "Camera Site":      "camera_site",
    "Latitude":         "latitude",
    "Longitude":        "longitude",
    "port":             "port",
    "STATUS":           "status",
}


def fetch_arlington_data(url):
    """Fetch and normalize fresh data from Arlington API."""
    print(f"Fetching data from Arlington API...")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    raw = response.json()

    # Arlington API may wrap data in a 'value' key (OData format)
    records = raw.get("value", raw) if isinstance(raw, dict) else raw

    normalized = []
    for r in records:
        cam = {}
        for api_field, local_field in FIELD_MAP.items():
            value = r.get(api_field, r.get(local_field, None))
            if value is not None:
                # Normalize types
                if local_field in ("latitude", "longitude"):
                    value = float(value)
                elif local_field == "status":
                    value = str(value).upper()
                else:
                    value = str(value)
            cam[local_field] = value
        normalized.append(cam)

    print(f"  Fetched {len(normalized)} cameras from API")
    return normalized


def load_local_data(path):
    """Load current cleaned JSON."""
    print(f"Loading local data from {path}...")
    with open(path, "r") as f:
        data = json.load(f)
    print(f"  Loaded {len(data)} cameras from local file")
    return data


def index_by_site(cameras):
    """Index camera list by camera_site for easy lookup."""
    return {c["camera_site"]: c for c in cameras if c.get("camera_site")}


def diff_cameras(local_cameras, fresh_cameras):
    """Compare local vs fresh data and return a structured diff."""
    local_index = index_by_site(local_cameras)
    fresh_index = index_by_site(fresh_cameras)

    local_sites = set(local_index.keys())
    fresh_sites = set(fresh_index.keys())

    added = []
    removed = []
    changed = []

    # New cameras in fresh data
    for site in fresh_sites - local_sites:
        added.append(fresh_index[site])

    # Cameras removed from fresh data
    for site in local_sites - fresh_sites:
        removed.append(local_index[site])

    # Cameras that exist in both — check for changes
    for site in local_sites & fresh_sites:
        local_cam = local_index[site]
        fresh_cam = fresh_index[site]
        field_changes = {}
        for field in ("camera_name", "latitude", "longitude", "port", "status"):
            local_val = local_cam.get(field)
            fresh_val = fresh_cam.get(field)
            if local_val != fresh_val:
                field_changes[field] = {"old": local_val, "new": fresh_val}
        if field_changes:
            changed.append({
                "camera_site": site,
                "camera_name": local_cam.get("camera_name"),
                "changes": field_changes
            })

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "total_local": len(local_cameras),
            "total_fresh": len(fresh_cameras),
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def print_diff_report(diff):
    """Print a human-readable summary of the diff."""
    s = diff["summary"]
    print("\n" + "="*50)
    print("DIFF REPORT")
    print("="*50)
    print(f"Timestamp : {diff['timestamp']}")
    print(f"Local     : {s['total_local']} cameras")
    print(f"Fresh     : {s['total_fresh']} cameras")
    print(f"Added     : {s['added']}")
    print(f"Removed   : {s['removed']}")
    print(f"Changed   : {s['changed']}")
    print("="*50)

    if diff["added"]:
        print("\nNEW CAMERAS:")
        for cam in diff["added"]:
            print(f"  + {cam['camera_site']}: {cam['camera_name']}")

    if diff["removed"]:
        print("\nREMOVED CAMERAS:")
        for cam in diff["removed"]:
            print(f"  - {cam['camera_site']}: {cam['camera_name']}")

    if diff["changed"]:
        print("\nCHANGED CAMERAS:")
        for cam in diff["changed"]:
            print(f"  ~ {cam['camera_site']}: {cam['camera_name']}")
            for field, vals in cam["changes"].items():
                print(f"      {field}: {vals['old']} → {vals['new']}")

    if not any([diff["added"], diff["removed"], diff["changed"]]):
        print("\nNo changes detected. Local data is up to date.")


def save_diff_report(diff, path="diff_report.json"):
    """Save the diff report to a JSON file."""
    with open(path, "w") as f:
        json.dump(diff, f, indent=2)
    print(f"\nDiff report saved to {path}")


if __name__ == "__main__":
    fresh_cameras = fetch_arlington_data(ARLINGTON_API_URL)
    local_cameras = load_local_data(LOCAL_JSON_PATH)
    diff = diff_cameras(local_cameras, fresh_cameras)
    print_diff_report(diff)
    save_diff_report(diff)