"""Local NHL API proxy for Hockey Untapped.

Run from the folder containing the tracker:
    py nhl_api_server.py
Then open http://localhost:8000/v4_stat_tracker.html
"""

import json
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.parse import quote
from urllib.request import Request, urlopen

NHL_BASE = "https://api-web.nhle.com/v1"
HOST = "127.0.0.1"
PORT = 8000


class HockeyUntappedHandler(SimpleHTTPRequestHandler):
    server_version = "HockeyUntappedLocal/1.0"

    def _send_json(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy_nhl(self, endpoint):
        request = Request(
            NHL_BASE + endpoint,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; HockeyUntapped/1.0)",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type", "application/json")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except HTTPError as exc:
            detail = exc.read(1000).decode("utf-8", errors="replace")
            self._send_json(exc.code, {"error": f"NHL API returned HTTP {exc.code}", "details": detail})
        except (URLError, TimeoutError, OSError) as exc:
            self._send_json(502, {"error": f"Could not reach NHL API: {exc}"})
        except Exception as exc:
            self._send_json(500, {"error": f"Unexpected proxy error: {exc}"})

    def do_GET(self):
        path = urlparse(self.path).path

        # Open the actual tracker filename at the site root.
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/v4_stat_tracker.html")
            self.end_headers()
            return

        # Backward-compatible current-day scoreboard route.
        if path == "/api/score/now":
            return self._proxy_nhl("/score/now")

        # Tracker's date-specific scoreboard request.
        match = re.fullmatch(r"/api/score/(\d{4}-\d{2}-\d{2})", path)
        if match:
            return self._proxy_nhl("/score/" + match.group(1))

        # NHL gamecenter endpoints used by the tracker.
        match = re.fullmatch(r"/api/game/(\d{8,12})/(landing|play-by-play)", path)
        if match:
            game_id, resource = match.groups()
            return self._proxy_nhl(f"/gamecenter/{game_id}/{resource}")

        if path.startswith("/api/"):
            return self._send_json(404, {"error": "Unknown API route", "path": path})

        return super().do_GET()

    def log_message(self, fmt, *args):
        # Keep the console useful without printing every static asset request.
        if "api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), HockeyUntappedHandler)
    print(f"Hockey Untapped API server running at http://localhost:{PORT}")
    print("Open http://localhost:8000/v4_stat_tracker.html")
    print("Keep this window open while using the tracker. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
