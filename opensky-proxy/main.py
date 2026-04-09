"""
OpenSky Proxy — Google Cloud Function (anonymous, no OAuth)
Proxies the OpenSky anonymous endpoint to avoid browser CORS restrictions.
No credentials needed — just acts as a pass-through with CORS headers.
"""

import json
import requests
import functions_framework
from datetime import datetime, timezone

LAT_MIN, LAT_MAX =  38.70,  39.10
LON_MIN, LON_MAX = -77.40, -76.80

OPENSKY_URL = (
    f"https://opensky-network.org/api/states/all"
    f"?lamin={LAT_MIN}&lomin={LON_MIN}&lamax={LAT_MAX}&lomax={LON_MAX}"
)

FIELDS = [
    "icao24","callsign","origin_country","time_position","last_contact",
    "longitude","latitude","baro_altitude","on_ground","velocity",
    "true_track","vertical_rate","sensors","geo_altitude","squawk",
    "spi","position_source"
]

@functions_framework.http
def opensky_proxy(request):
    cors = {"Access-Control-Allow-Origin": "*"}

    if request.method == "OPTIONS":
        return ("", 204, {**cors,
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Content-Type",
        })

    try:
        res = requests.get(OPENSKY_URL, timeout=20)
        res.raise_for_status()
        raw = res.json()

        aircraft = []
        for state in (raw.get("states") or []):
            r = {FIELDS[i]: state[i] for i in range(min(len(state), len(FIELDS)))}
            if r.get("latitude") is None or r.get("longitude") is None:
                continue
            alt  = r.get("baro_altitude") or r.get("geo_altitude")
            vel  = r.get("velocity")
            vr   = r.get("vertical_rate")
            aircraft.append({
                "icao24":       r.get("icao24",""),
                "callsign":     (r.get("callsign") or "").strip() or "Unknown",
                "country":      r.get("origin_country",""),
                "latitude":     round(r["latitude"], 5),
                "longitude":    round(r["longitude"], 5),
                "altitude_ft":  round(alt * 3.28084) if alt else None,
                "speed_kts":    round(vel * 1.94384) if vel else None,
                "heading":      r.get("true_track"),
                "vertical_fpm": round(vr * 196.85) if vr else None,
                "on_ground":    r.get("on_ground", False),
                "squawk":       r.get("squawk"),
            })

        return (
            json.dumps({"aircraft": aircraft, "count": len(aircraft),
                        "timestamp": datetime.now(timezone.utc).isoformat()}),
            200,
            {**cors, "Content-Type": "application/json"}
        )

    except Exception as e:
        return (json.dumps({"error": str(e)}), 500,
                {**cors, "Content-Type": "application/json"})