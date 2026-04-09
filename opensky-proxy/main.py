"""
OpenSky Proxy — Google Cloud Function
Securely proxies requests to the OpenSky Network API.

Fundamental concept:
- This function runs server-side in Google Cloud
- Your client_id and client_secret live here as environment variables
- The browser never sees your credentials
- The browser just calls this function's URL and gets flight data back

Deploy with:
  gcloud functions deploy opensky-proxy \
    --runtime python311 \
    --trigger-http \
    --allow-unauthenticated \
    --set-env-vars OPENSKY_CLIENT_ID=your_id,OPENSKY_CLIENT_SECRET=your_secret \
    --region us-east4
"""

import os
import json
import requests
import functions_framework
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────
# Bounding box around DCA / Arlington airspace
# Wider than Arlington itself so we see approaching aircraft
LAT_MIN = 38.70
LAT_MAX = 39.10
LON_MIN = -77.40
LON_MAX = -76.80

OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"

# State vector field indices (OpenSky returns arrays, not dicts)
# Fundamental concept: OpenSky returns each aircraft as an array
# to minimize payload size. We map indices to field names.
FIELDS = [
    "icao24",        # 0  — unique transponder hex address
    "callsign",      # 1  — flight number / callsign
    "origin_country",# 2  — country of registration
    "time_position", # 3  — unix timestamp of last position
    "last_contact",  # 4  — unix timestamp of last message
    "longitude",     # 5
    "latitude",      # 6
    "baro_altitude", # 7  — barometric altitude in meters
    "on_ground",     # 8  — true if surface position report
    "velocity",      # 9  — ground speed in m/s
    "true_track",    # 10 — heading in degrees (0 = north)
    "vertical_rate", # 11 — climb/descent rate in m/s
    "sensors",       # 12 — sensor serial numbers
    "geo_altitude",  # 13 — geometric altitude in meters
    "squawk",        # 14 — transponder squawk code
    "spi",           # 15 — special purpose indicator
    "position_source"# 16 — 0=ADS-B, 1=ASTERIX, 2=MLAT
]


def get_opensky_token():
    """
    Exchange client credentials for an OAuth2 bearer token.

    Fundamental concept: OAuth2 client credentials flow
    - We send our client_id + client_secret to the auth server
    - The auth server returns a short-lived access token
    - We use that token to authenticate API requests
    - This keeps secrets off the wire for actual data requests
    """
    client_id     = os.environ.get("OPENSKY_CLIENT_ID")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET must be set")

    response = requests.post(
        OPENSKY_TOKEN_URL,
        data={
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
        },
        timeout=10
    )
    response.raise_for_status()
    return response.json()["access_token"]


def fetch_aircraft(token):
    """Fetch all aircraft in the DCA/Arlington bounding box."""
    response = requests.get(
        OPENSKY_STATES_URL,
        headers={"Authorization": f"Bearer {token}"},
        params={
            "lamin": LAT_MIN,
            "lomin": LON_MIN,
            "lamax": LAT_MAX,
            "lomax": LON_MAX,
        },
        timeout=15
    )
    response.raise_for_status()
    return response.json()


def format_aircraft(states_json):
    """
    Convert OpenSky's raw array format into clean named dicts.
    Filter out aircraft with no position data.
    """
    aircraft = []
    states = states_json.get("states") or []

    for state in states:
        # Map array indices to field names
        record = {FIELDS[i]: state[i] for i in range(min(len(state), len(FIELDS)))}

        # Skip aircraft with no position
        if record.get("latitude") is None or record.get("longitude") is None:
            continue

        # Convert units for the frontend
        velocity_ms  = record.get("velocity")
        altitude_m   = record.get("baro_altitude") or record.get("geo_altitude")
        vertical_ms  = record.get("vertical_rate")

        aircraft.append({
            "icao24":        record.get("icao24", ""),
            "callsign":      (record.get("callsign") or "").strip() or "Unknown",
            "country":       record.get("origin_country", ""),
            "latitude":      round(record.get("latitude"), 5),
            "longitude":     round(record.get("longitude"), 5),
            "altitude_ft":   round(altitude_m * 3.28084) if altitude_m else None,
            "speed_kts":     round(velocity_ms * 1.94384) if velocity_ms else None,
            "heading":       record.get("true_track"),
            "vertical_fpm":  round(vertical_ms * 196.85) if vertical_ms else None,
            "on_ground":     record.get("on_ground", False),
            "squawk":        record.get("squawk"),
        })

    return aircraft


@functions_framework.http
def opensky_proxy(request):
    """
    Main Cloud Function entry point.
    Handles CORS so the browser can call this from any origin.

    Fundamental concept: CORS (Cross-Origin Resource Sharing)
    - Browsers block JavaScript from calling APIs on different domains
    - Our map is on storage.googleapis.com
    - OpenSky is on opensky-network.org
    - Without CORS headers the browser would block the response
    - By adding CORS headers here, we tell the browser it's safe
    """

    # Handle CORS preflight request
    if request.method == "OPTIONS":
        return ("", 204, {
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age":       "3600",
        })

    cors_headers = {"Access-Control-Allow-Origin": "*"}

    try:
        token    = get_opensky_token()
        raw      = fetch_aircraft(token)
        aircraft = format_aircraft(raw)

        return (
            json.dumps({
                "aircraft": aircraft,
                "count":    len(aircraft),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "bounds": {
                    "lat_min": LAT_MIN, "lat_max": LAT_MAX,
                    "lon_min": LON_MIN, "lon_max": LON_MAX,
                }
            }),
            200,
            {**cors_headers, "Content-Type": "application/json"}
        )

    except requests.exceptions.HTTPError as e:
        return (
            json.dumps({"error": f"OpenSky API error: {str(e)}"}),
            502,
            {**cors_headers, "Content-Type": "application/json"}
        )
    except Exception as e:
        return (
            json.dumps({"error": str(e)}),
            500,
            {**cors_headers, "Content-Type": "application/json"}
        )
