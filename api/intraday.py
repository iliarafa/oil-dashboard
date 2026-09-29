"""GET /api/intraday — today's 5-minute closes for each market."""

from http.server import BaseHTTPRequestHandler
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?range={range}&interval={interval}"
)

MARKETS = {
    "wti": ("CL=F", 2),
    "brent": ("BZ=F", 2),
    "heating-oil": ("HO=F", 4),
}

CACHE = "public, s-maxage=55, stale-while-revalidate=30"


def fetch_chart(symbol: str, rng: str, interval: str):
    url = CHART_URL.format(
        symbol=urllib.parse.quote(symbol), range=rng, interval=interval
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.load(resp)
    result = (payload.get("chart") or {}).get("result")
    if not result:
        raise ValueError("no data in response")
    return result[0]


def closes(result):
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    return [(ts, c) for ts, c in zip(stamps, quote.get("close") or []) if c is not None]


def load_intraday(symbol: str, dec: int):
    result = fetch_chart(symbol, "1d", "5m")
    return {"points": [[ts * 1000, round(c, dec)] for ts, c in closes(result)]}


def build_payload():
    markets = {}
    errors = []
    for key, (symbol, dec) in MARKETS.items():
        try:
            markets[key] = load_intraday(symbol, dec)
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({"market": key, "message": str(exc)})
    fetched_at = None
    if markets:
        fetched_at = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    data = {"fetchedAt": fetched_at, "markets": markets, "errors": errors}
    if not markets:
        data["error"] = (
            "Could not reach Yahoo Finance. The board will try again in a moment."
        )
    status = 200 if markets else 502
    return status, data


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, data = build_payload()
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", CACHE)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return
