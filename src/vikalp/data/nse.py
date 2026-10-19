"""Public NSE option-chain snapshot connector.

Fetches the same public JSON endpoints the nseindia.com website itself uses, in
your own session — Vikalp never caches or redistributes exchange data.

Notes:
- NSE throttles aggressively; warm the session with the homepage first and keep
  calls modest. For anything beyond personal/analytical use, use a broker API
  (Kite Connect, Upstox, Fyers) — see ``vikalp.data.brokers``.
- Endpoints are unofficial and may change; failures raise ``DataProviderError``
  with an actionable message rather than crashing the caller.
"""

from __future__ import annotations

import httpx

BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE}/option-chain",
}

# Underlying symbol → NSE option-chain endpoint query
EQUITY = "option-chain-equity"
INDEX = "option-chain-indices"
INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}


class DataProviderError(RuntimeError):
    pass


def _client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=15.0, follow_redirects=True)


def fetch_option_chain(symbol: str, client: httpx.Client | None = None) -> dict:
    """Return the raw NSE option-chain payload for ``symbol`` (e.g. 'CANBK', 'NIFTY')."""
    symbol = symbol.upper().strip()
    kind = INDEX if symbol in INDEX_SYMBOLS else EQUITY
    own = client is None
    client = client or _client()
    try:
        # warm-up: NSE sets cookies on the homepage before serving API JSON
        client.get(BASE, headers={"Referer": None} if False else None)
        url = f"{BASE}/api/{kind}?symbol={symbol}"
        r = client.get(url)
        if r.status_code == 401 or r.text.strip().startswith("<"):
            raise DataProviderError(
                "NSE rejected the request (cookie/throttle). "
                "Retry after a pause, or use a broker API key (Kite/Upstox/Fyers)."
            )
        if r.status_code != 200:
            raise DataProviderError(f"NSE returned HTTP {r.status_code} for {symbol}")
        return r.json()
    except httpx.HTTPError as e:
        raise DataProviderError(f"network error fetching NSE chain: {e}") from e
    finally:
        if own:
            client.close()


def normalize_chain(raw: dict, lot_size_hint: int | None = None) -> list[dict]:
    """Flatten NSE payload into rows: {strike, ce:{...}, pe:{...}} sorted by strike.

    OI is reported in contracts (NSE reports raw units; lot conversion is applied
    by the caller when lot sizes are known).
    """
    records = (raw.get("records") or {}).get("data") or []
    rows: list[dict] = []
    for rec in records:
        strike = rec.get("strikePrice")
        if strike is None:
            continue
        row: dict = {"strike": strike, "expiry": rec.get("expiryDate")}
        for side in ("CE", "PE"):
            o = rec.get(side) or {}
            row[side.lower()] = {
                "ltp": o.get("lastPrice"),
                "bid": o.get("bidprice"),
                "ask": o.get("askPrice"),
                "oi": o.get("openInterest"),
                "volume": o.get("totalTradedVolume"),
                "iv": o.get("impliedVolatility"),
                "change_in_oi": o.get("changeinOpenInterest"),
            }
        rows.append(row)
    rows.sort(key=lambda r: r["strike"])
    return rows


def summary_stats(rows: list[dict]) -> dict:
    """PCR (OI), max pain, and largest CE/PE walls from normalized rows."""
    if not rows:
        return {}
    ce_oi = {r["strike"]: r["ce"]["oi"] or 0 for r in rows}
    pe_oi = {r["strike"]: r["pe"]["oi"] or 0 for r in rows}
    total_ce = sum(ce_oi.values())
    total_pe = sum(pe_oi.values())

    strikes = sorted(ce_oi)
    max_pain, best = None, float("inf")
    for k in strikes:  # strike where total writer pain is minimized
        pain = sum(max(k - s, 0) * ce_oi[s] + max(s - k, 0) * pe_oi[s] for s in strikes)
        if pain < best:
            best, max_pain = pain, k

    return {
        "pcr_oi": round(total_pe / total_ce, 3) if total_ce else None,
        "max_pain": max_pain,
        "ce_wall_strike": max(ce_oi, key=ce_oi.get),
        "ce_wall_oi": max(ce_oi.values()),
        "pe_wall_strike": max(pe_oi, key=pe_oi.get),
        "pe_wall_oi": max(pe_oi.values()),
        "disclaimer": "estimates from public snapshot; not investment advice",
    }
