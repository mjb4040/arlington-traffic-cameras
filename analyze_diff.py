"""
Data Stewardship Agent - Step 3: Claude Reasoning Layer
Reads the diff report and asks Claude to analyze it, flag anomalies,
and produce a plain-English summary before any changes are applied.
"""

import json
import os
import requests

# --- Config ---
DIFF_REPORT_PATH = "diff_report.json"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = "claude-opus-4-6"


def load_diff_report(path):
    """Load the diff report produced by diff_cameras.py"""
    print(f"Loading diff report from {path}...")
    with open(path, "r") as f:
        return json.load(f)


def build_prompt(diff):
    """Build the prompt we'll send to Claude."""
    return f"""You are a data stewardship agent for an Arlington County traffic camera web app.

Your job is to review a diff between the app's current camera dataset and fresh data from Arlington County's open data portal, then produce a clear analysis before any changes are applied.

Here is the diff report:

{json.dumps(diff, indent=2)}

Please analyze this diff and provide:

1. SUMMARY
   A plain-English summary of what changed and how significant it is.

2. ANOMALIES
   Flag anything suspicious or that warrants human review before applying. 
   Look for things like:
   - Cameras that appear to have swapped names/locations with each other
   - Cameras with missing or invalid data (None, #N/A, etc.)
   - Large coordinate shifts that seem unlikely for a physical camera
   - Port format changes (e.g. full RTSP URLs vs just port numbers)
   - Anything else that looks like a data quality issue

3. SAFE TO AUTO-APPLY
   List which changes look clean and safe to apply automatically.

4. NEEDS HUMAN REVIEW
   List which changes should be reviewed by a human before applying,
   and explain why for each one.

5. RECOMMENDATION
   Should this diff be applied as-is, partially applied, or held for 
   human review? Give a clear recommendation.

Be specific and reference camera IDs and names in your analysis.
"""


def ask_claude(prompt):
    """Send the prompt to Claude and return the response."""
    print("Sending diff to Claude for analysis...")

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": MODEL,
        "max_tokens": 2000,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    response = requests.post(ANTHROPIC_API_URL, headers=headers, json=body)
    response.raise_for_status()
    data = response.json()
    return data["content"][0]["text"]


def save_analysis(analysis, path="claude_analysis.txt"):
    """Save Claude's analysis to a text file."""
    with open(path, "w") as f:
        f.write(analysis)
    print(f"Analysis saved to {path}")


if __name__ == "__main__":
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        print("Run: export ANTHROPIC_API_KEY=your_key_here")
        exit(1)

    diff = load_diff_report(DIFF_REPORT_PATH)
    prompt = build_prompt(diff)
    analysis = ask_claude(prompt)

    print("\n" + "="*60)
    print("CLAUDE'S ANALYSIS")
    print("="*60)
    print(analysis)
    print("="*60)

    save_analysis(analysis)