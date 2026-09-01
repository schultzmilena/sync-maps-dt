"""

Run:  python sync_maps.py
Open: http://localhost:8000


"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any
from urllib.parse import urlparse


@dataclass
class Robot:
    id: str
    latitude: float
    longitude: float
    status: str = "online"
    battery: int = 100


class RobotStore:

    def __init__(self) -> None:
        self._robots: dict[str, Robot] = {
            "robot": Robot("robot", -30.076389, -51.236111, battery=87)
        }
        self._lock = Lock()

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(robot) for robot in self._robots.values()]

    def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        robot_id = str(data.get("id", "")).strip()
        if not robot_id:
            raise ValueError("'id' is required")
        try:
            latitude = float(data["latitude"])
            longitude = float(data["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("'latitude' and 'longitude' must be numbers") from exc
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("coordinates are outside their valid ranges")

        robot = Robot(
            id=robot_id, latitude=latitude, longitude=longitude,
            status=str(data.get("status", "online")),
            battery=max(0, min(100, int(data.get("battery", 100)))),
        )
        with self._lock:
            self._robots[robot.id] = robot
        return asdict(robot)


ROBOTS = RobotStore()


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Robot map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  * { box-sizing: border-box } body { margin: 0; font: 14px system-ui, sans-serif; display: grid; grid-template-columns: 310px 1fr; height: 100vh }
  aside { padding: 22px; border-right: 1px solid #ddd; background: #fcfcfc } h1 { font-size: 22px; margin-top: 0 } label { display:block; margin-top: 12px; font-weight:600 } input, select, button { width:100%; padding:9px; margin-top:4px; border:1px solid #bbb; border-radius:5px } button { margin-top:18px; border:0; background:#1565c0; color:white; cursor:pointer } #hint { color:#555; line-height:1.4 } #map { height:100vh }
  @media (max-width: 650px) { body { grid-template-columns: 1fr; grid-template-rows:auto 1fr } aside { border-right:0; border-bottom:1px solid #ddd; padding:14px } #map { height:auto } label { display:inline-block; width:48% } }
</style></head><body>
<aside><h1>Robot fleet</h1><p id="hint">Click the map to fill coordinates, then save a robot. Saving an existing ID moves it.</p>
<form id="robot-form"><label>Robot ID<input id="id" required placeholder="robot-2"></label>
<label>Latitude<input id="latitude" required type="number" step="any"></label><label>Longitude<input id="longitude" required type="number" step="any"></label>
<label>Status<select id="status"><option>online</option><option>charging</option><option>offline</option></select></label>
<label>Battery (%)<input id="battery" type="number" min="0" max="100" value="100"></label><button>Save robot</button></form></aside>
<main id="map"></main><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const map = L.map('map').setView([-30.076389, -51.236111], 13), markers = new Map();
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
function icon(status) { return status === 'offline' ? '🔴' : status === 'charging' ? '⚡' : '🤖'; }
async function refresh() { const robots = await (await fetch('/api/robots')).json(); robots.forEach(r => { const p=[r.latitude,r.longitude], label=`${icon(r.status)} <b>${r.id}</b><br>${r.status} · ${r.battery}%`; if (markers.has(r.id)) markers.get(r.id).setLatLng(p).bindPopup(label); else markers.set(r.id,L.marker(p).addTo(map).bindPopup(label)); }); }
map.on('click', e => { latitude.value=e.latlng.lat.toFixed(6); longitude.value=e.latlng.lng.toFixed(6); });
document.querySelector('form').onsubmit = async e => { e.preventDefault(); const robot={id:id.value,latitude:+latitude.value,longitude:+longitude.value,status:status.value,battery:+battery.value}; const response=await fetch('/api/robots',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(robot)}); if (!response.ok) return alert((await response.json()).error); await refresh(); map.setView([robot.latitude,robot.longitude],16); };
refresh(); setInterval(refresh, 3000);
</script></body></html>"""


class RobotMapHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if urlparse(self.path).path == "/":
            self._send(HTTPStatus.OK, PAGE, "text/html; charset=utf-8")
        elif urlparse(self.path).path == "/api/robots":
            self._send_json(HTTPStatus.OK, ROBOTS.all())
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/robots":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length))
            self._send_json(HTTPStatus.OK, ROBOTS.upsert(data))
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def _send_json(self, status: HTTPStatus, data: Any) -> None:
        self._send(status, json.dumps(data), "application/json")

    def _send(self, status: HTTPStatus, body: str, content_type: str) -> None:
        encoded = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), RobotMapHandler)
    print("Robot map running at http://localhost:8000 (Ctrl-C to stop)")
    server.serve_forever()
