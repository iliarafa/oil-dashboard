#!/usr/bin/env python3
"""Oil Price Board: a local dashboard for WTI, Brent and heating oil futures.

Run it with `python3 server.py` and it opens http://localhost:8787 in your
browser. Quotes come from Yahoo Finance and refresh every minute. Uses only
the Python standard library.
"""

import argparse
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval={interval}"

# Board key -> (Yahoo symbol, price decimals)
MARKETS = {
    "wti": ("CL=F", 2),
    "brent": ("BZ=F", 2),
    "heating-oil": ("HO=F", 4),
}

CACHE_SECONDS = 55  # at most one upstream fetch per market per minute
RETRY_SECONDS = 15  # after a failed fetch


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_chart(symbol, rng, interval):
    url = CHART_URL.format(symbol=urllib.parse.quote(symbol), range=rng, interval=interval)
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


def load_quote(symbol, dec):
    """Latest quote plus one year of daily closes."""
    result = fetch_chart(symbol, "1y", "1d")
    meta = result["meta"]
    tz = timezone(timedelta(seconds=meta.get("gmtoffset", 0)))
    history = []
    for ts, c in closes(result):
        day = datetime.fromtimestamp(ts, tz).date().isoformat()
        if history and history[-1][0] == day:
            history[-1][1] = round(c, dec)
        else:
            history.append([day, round(c, dec)])

    price = meta["regularMarketPrice"]
    change = meta.get("fulldayChange")
    if change is None and len(history) > 1:
        change = price - history[-2][1]
    pct = None
    if change is not None and price != change:
        pct = round(change / (price - change) * 100, 3)
    month = re.search(r"([A-Z][a-z]{2}) (\d{2})$", meta.get("shortName") or "")
    return {
        "symbol": symbol,
        "contract": f"{month.group(1)} {month.group(2)}" if month else None,
        "exchange": meta.get("exchangeName"),
        "price": round(price, dec),
        "change": round(change, dec) if change is not None else None,
        "changePct": pct,
        "dayLow": meta.get("regularMarketDayLow"),
        "dayHigh": meta.get("regularMarketDayHigh"),
        "low52": meta.get("fiftyTwoWeekLow"),
        "high52": meta.get("fiftyTwoWeekHigh"),
        "marketTime": iso(meta["regularMarketTime"]),
        "history": history,
    }


def load_intraday(symbol, dec):
    """Today's session in 5-minute steps, as [epoch ms, close] pairs."""
    result = fetch_chart(symbol, "1d", "5m")
    return {"points": [[ts * 1000, round(c, dec)] for ts, c in closes(result)]}


class Feed:
    """Caches one kind of payload for all markets and refetches it when it goes stale.

    A market that fails to load keeps its last good value, so one bad
    response never blanks the board.
    """

    def __init__(self, loader):
        self.loader = loader
        self.lock = threading.Lock()
        self.markets = {}
        self.errors = []
        self.fetched_at = None
        self.next_fetch = 0.0

    def get(self):
        with self.lock:
            if time.time() >= self.next_fetch:
                self.refresh()
            return {
                "fetchedAt": self.fetched_at,
                "markets": self.markets,
                "errors": self.errors,
            }

    def refresh(self):
        errors = []
        for key, (symbol, dec) in MARKETS.items():
            try:
                self.markets[key] = self.loader(symbol, dec)
            except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as exc:
                errors.append({"market": key, "message": str(exc)})
        self.errors = errors
        if len(errors) < len(MARKETS):
            self.fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        self.next_fetch = time.time() + (RETRY_SECONDS if errors else CACHE_SECONDS)


FEEDS = {
    "/api/quotes": Feed(load_quote),
    "/api/intraday": Feed(load_intraday),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self.send_body(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path in FEEDS:
            data = FEEDS[path].get()
            status = 200 if data["markets"] else 502
            if not data["markets"]:
                data["error"] = "Could not reach Yahoo Finance. The board will try again in a moment."
            self.send_body(status, json.dumps(data).encode(), "application/json")
        else:
            self.send_body(404, b"Not found", "text/plain; charset=utf-8")

    def send_body(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet


def main():
    parser = argparse.ArgumentParser(description="Serve the Oil Price Board on your computer.")
    parser.add_argument("--port", type=int, default=8787, help="port to listen on (default 8787)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the board in a browser")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"Oil Price Board running at {url}  (press Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
