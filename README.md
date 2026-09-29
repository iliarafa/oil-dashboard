# Oil Price Board

Live board for WTI (`CL=F`), Brent (`BZ=F`), and heating oil (`HO=F`) futures.

## Production

Deployed on Vercel. Static `index.html` calls `/api/quotes` and `/api/intraday`.
Those routes are Python serverless functions that proxy Yahoo Finance and set
`Cache-Control: public, s-maxage=55` so the CDN caches for ~one minute.

Yahoo sometimes rate-limits datacenter IPs — if panels go empty, wait and refresh.

## Local

```bash
python3 server.py
# opens http://localhost:8787
```

Local server keeps an in-process 55s cache. Production relies on the CDN header instead.

## Layout

- `index.html` — frontend (unchanged relative `/api` paths)
- `api/quotes.py` / `api/intraday.py` — Vercel Python functions
- `api/_feed.py` — shared Yahoo loaders
- `server.py` — optional local stdlib server
