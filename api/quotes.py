"""GET /api/quotes — WTI, Brent, heating oil quotes + daily history."""

from http.server import BaseHTTPRequestHandler
import json

from _feed import build_payload, load_quote

CACHE = "public, s-maxage=55, stale-while-revalidate=30"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, data = build_payload(load_quote)
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", CACHE)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return
