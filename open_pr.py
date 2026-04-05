"""
Data Stewardship Agent - Step 4 (updated): GitHub PR Opener
Creates a new branch, applies only safe changes to cameras.json,
and opens a Pull Request with Claude's analysis as the description.

Fundamentals:
- We talk to GitHub via their REST API using HTTP requests
- Authentication uses your Personal Access Token in the header
- Git branching: we never write directly to main — always branch first
- Base64: GitHub's API requires file contents to be Base64 encoded
- Input validation: always verify external data fits your domain constraints
"""

import json
import os
import base64
import requests
from datetime import datetime

# --- Config ---
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
REPO_OWNER        = "mjb4040"
REPO_NAME         = "arlington-traffic-cameras"
BASE_BRANCH       = "main"
LOCAL_JSON_PATH   = "traffic_cameras_clean.json"
DIFF_REPORT_PATH  = "diff_report.json"
ANALYSIS_PATH     = "claude_analysis.txt"

GITHUB_API        = "https://api.github.com"
HEADERS           = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

# Arlington County geographic bounding box
# Any camera outside these bounds is physically impossible
LAT_MIN, LAT_MAX =  38.80,  39.00
LNG_MIN, LNG_MAX = -77.30, -76.90

# Known bad camera sites to exclude regardless of source data
BLOCKLIST = {"cam294"}  # positive longitude — places camera in western China


# ── Helpers ──────────────────────────────────────────────────────────────────

def github_get(path):
    """Send a GET request to the GitHub API."""
    r = requests.get(f"{GITHUB_API}{path}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def github_post(path, body):
    """Send a POST request to the GitHub API."""
    r = requests.post(f"{GITHUB_API}{path}", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json()


def github_put(path, body):
    """Send a PUT request to the GitHub API."""
    r = requests.put(f"{GITHUB_API}{path}", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json()


# ── Step 1: Apply only safe changes ──────────────────────────────────────────

def is_valid_coordinate(cam):
    """
    Validate that a camera's coordinates fall within Arlington County.

    Fundamentals:
    - This is domain validation — we're not just checking data types,
      we're checking whether the values make sense for our specific use case
    - Bounding box checks are a standard geospatial validation technique
    """
    lat = cam.get("latitude")
    lng = cam.get("longitude")
    if lat is None or lng is None:
        return False
    return LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX


def apply_safe_changes(local_cameras, diff):
    """
    Apply only the changes Claude flagged as safe.

    Fundamentals:
    - We read Claude's analysis to find which camera_sites are safe
    - We only modify the local dataset for those specific cameras
    - Everything else stays exactly as it was
    """
    print("Applying safe changes to local dataset...")

    # Index current cameras by site for easy lookup
    # Also remove any blocklisted cameras from the existing dataset
    camera_index = {}
    for c in local_cameras:
        site = c["camera_site"]
        if site in BLOCKLIST:
            print(f"  Removing blocklisted camera: {site}")
            continue
        camera_index[site] = c

    # Apply safe additions (new cameras with no anomalies)
    safe_added = 0
    for cam in diff.get("added", []):
        site = cam.get("camera_site")
        name = cam.get("camera_name", "")

        # Skip blocklisted cameras
        if site in BLOCKLIST:
            print(f"  Skipping blocklisted camera: {site}")
            continue

        # Skip cameras with invalid names
        if name in (None, "", "#N/A"):
            print(f"  Skipping {site}: invalid name")
            continue

        # Skip cameras with inconsistent casing (Cam vs cam)
        if site and site[0].isupper():
            print(f"  Skipping {site}: inconsistent casing")
            continue

        # Skip cameras outside Arlington's geographic bounding box
        if not is_valid_coordinate(cam):
            print(f"  Skipping {site}: coordinates outside Arlington bounds "
                  f"(lat={cam.get('latitude')}, lng={cam.get('longitude')})")
            continue

        camera_index[site] = cam
        safe_added += 1
        print(f"  + Added {site}: {name}")

    # Apply safe status-only changes (no location or name changes)
    safe_changed = 0
    for change in diff.get("changed", []):
        site    = change["camera_site"]
        changes = change["changes"]

        # Only apply if the ONLY change is status — nothing else
        if list(changes.keys()) == ["status"]:
            if site in camera_index:
                old = changes["status"]["old"]
                new = changes["status"]["new"]
                camera_index[site]["status"] = new
                safe_changed += 1
                print(f"  ~ Updated {site} status: {old} → {new}")
        else:
            print(f"  Skipping {site}: has non-status changes (needs human review)")

    # Removals — conservative: flag for human review, don't auto-remove
    for cam in diff.get("removed", []):
        site = cam.get("camera_site")
        print(f"  Skipping removal of {site}: flagged for human review")

    print(f"\nSafe changes applied: {safe_added} added, {safe_changed} status updates")
    return list(camera_index.values())


# ── Step 2: Create a branch ───────────────────────────────────────────────────

def create_branch(branch_name):
    """
    Create a new git branch via the GitHub API.

    Fundamentals:
    - A branch is just a pointer to a commit
    - We get the SHA (unique ID) of the latest commit on main
    - Then we create a new branch pointing to that same commit
    - From that point, our changes diverge from main until we merge
    """
    print(f"\nCreating branch: {branch_name}")

    # Get the SHA of the latest commit on main
    ref_data = github_get(f"/repos/{REPO_OWNER}/{REPO_NAME}/git/ref/heads/{BASE_BRANCH}")
    sha = ref_data["object"]["sha"]
    print(f"  Base commit SHA: {sha[:7]}")

    # Create the new branch pointing to that SHA
    github_post(f"/repos/{REPO_OWNER}/{REPO_NAME}/git/refs", {
        "ref": f"refs/heads/{branch_name}",
        "sha": sha
    })
    print(f"  Branch created.")
    return sha


# ── Step 3: Push updated JSON ─────────────────────────────────────────────────

def push_updated_json(branch_name, updated_cameras):
    """
    Push the updated cameras.json to the new branch.

    Fundamentals:
    - GitHub's API requires file contents encoded in Base64
    - Base64 is a way to represent binary data as plain text
    - We also need the current file's SHA so GitHub knows what we're replacing
    """
    print(f"\nPushing updated JSON to branch: {branch_name}")

    # Get the current file's SHA from GitHub
    file_data = github_get(
        f"/repos/{REPO_OWNER}/{REPO_NAME}/contents/traffic_cameras_clean.json"
        f"?ref={BASE_BRANCH}"
    )
    file_sha = file_data["sha"]

    # Encode the updated JSON as Base64
    updated_json = json.dumps(updated_cameras, indent=2)
    encoded = base64.b64encode(updated_json.encode("utf-8")).decode("utf-8")

    # Push the file to the branch
    github_put(
        f"/repos/{REPO_OWNER}/{REPO_NAME}/contents/traffic_cameras_clean.json",
        {
            "message": f"agent: apply safe camera data updates",
            "content": encoded,
            "sha": file_sha,
            "branch": branch_name
        }
    )
    print("  JSON pushed successfully.")


# ── Step 4: Open the Pull Request ─────────────────────────────────────────────

def open_pull_request(branch_name, diff, analysis):
    """
    Open a Pull Request on GitHub.

    Fundamentals:
    - A PR is a formal request to merge one branch into another
    - The PR description is written in Markdown
    - This is the human-in-the-loop gate: nothing merges until you approve
    """
    print(f"\nOpening Pull Request...")

    s = diff["summary"]
    date = datetime.utcnow().strftime("%Y-%m-%d")

    pr_body = f"""## 🤖 Weekly Camera Data Update — {date}

### Summary
| Metric | Value |
|--------|-------|
| Cameras in current dataset | {s['total_local']} |
| Cameras in fresh API data | {s['total_fresh']} |
| New cameras detected | {s['added']} |
| Removed cameras detected | {s['removed']} |
| Changed cameras detected | {s['changed']} |

---

### Claude's Analysis

{analysis}

---

### What this PR applies
- ✅ New cameras with clean data
- ✅ Status-only changes (ONLINE/OFFLINE flips)
- ❌ Location/name changes held for human review
- ❌ Cameras with data quality issues held for human review

**Review the changes above and merge if you agree. Close this PR to reject.**
"""

    result = github_post(
        f"/repos/{REPO_OWNER}/{REPO_NAME}/pulls",
        {
            "title": f"[Agent] Camera data update — {date}",
            "body": pr_body,
            "head": branch_name,
            "base": BASE_BRANCH
        }
    )

    pr_url = result["html_url"]
    print(f"  Pull Request opened: {pr_url}")
    return pr_url


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Validate environment
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN environment variable not set.")
        exit(1)

    # Load inputs
    print("Loading diff report and Claude analysis...")
    with open(DIFF_REPORT_PATH) as f:
        diff = json.load(f)
    with open(ANALYSIS_PATH) as f:
        analysis = f.read()
    with open(LOCAL_JSON_PATH) as f:
        local_cameras = json.load(f)

    # Build branch name with today's date
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    branch_name = f"agent/camera-update-{date_str}"

    # Run the pipeline
    updated_cameras = apply_safe_changes(local_cameras, diff)
    create_branch(branch_name)
    push_updated_json(branch_name, updated_cameras)
    pr_url = open_pull_request(branch_name, diff, analysis)

    print(f"\n✅ Done. Review your PR at:\n{pr_url}")