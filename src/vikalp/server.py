"""Vikalp MCP server — option chains, greeks, payoff math and position analysis
for any MCP client (Claude Code, OpenCode, Cursor, Gemini CLI, ...).

Run:  vikalp-mcp        (or: python -m vikalp.server)
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .analytics.greeks import black_scholes, expected_move, implied_vol, risk_neutral_prob
from .analytics.strategy import Strategy

mcp = MCPServer(
    "vikalp",
    instructions=(
        "Vikalp is an options-analytics tool for Indian markets (NSE/BSE). "
        "Use these tools for option chains, Black-Scholes greeks/IV, multi-leg "
        "payoff analysis and position scoring. All outputs are estimates, "
        "never investment advice."
    ),
)

LOT_SIZES_HINT = {"NIFTY": 75, "BANKNIFTY": 35, "FINNIFTY": 65, "MIDCPNIFTY": 140}


@mcp.tool()
def greeks(
    spot: float,
    strike: float,
    t_days: float,
    iv: float,
    right: str = "C",
    market_price: float | None = None,
) -> dict:
    """Black-Scholes greeks for one option.

    Args:
        spot: underlying spot price
        strike: option strike
        t_days: calendar days to expiry
        iv: annualized implied volatility as a decimal (0.26 = 26%)
        right: 'C' for call, 'P' for put
        market_price: if given, IV is re-solved from this price instead of using `iv`
    """
    used_iv = iv
    solved_from = None
    if market_price is not None:
        solved = implied_vol(market_price, spot, strike, t_days, right)
        if solved is None:
            return {"error": "could not solve IV from market_price (out of bounds)"}
        used_iv, solved_from = solved, market_price
    _price, g = black_scholes(spot, strike, t_days, used_iv, right)
    low, high = expected_move(spot, t_days, used_iv)
    out = g.as_dict()
    out.update(
        {
            "iv_used": used_iv,
            "iv_solved_from_market_price": solved_from,
            "expected_move_1sigma": [low, high],
            "prob_ITM": risk_neutral_prob(spot, strike, t_days, used_iv)
            if right == "C"
            else round(1 - risk_neutral_prob(spot, strike, t_days, used_iv), 4),
            "disclaimer": "model estimate, not investment advice",
        }
    )
    return out


@mcp.tool()
def strategy_payoff(
    legs: list[dict], spot: float, t_days: float = 8, iv: float = 0.20, lot_size: int = 1
) -> dict:
    """Payoff analysis for a multi-leg option strategy at expiry.

    Args:
        legs: list of {strike, right ('C'/'P'), qty (+ long / - short), premium, lot_size?}
        spot: current underlying price
        t_days: calendar days to expiry
        iv: annualized IV for probability estimate (decimal)
        lot_size: shares per contract (e.g. 6750 for CANBK), or use per-leg lot_size
    """
    strat = Strategy(legs)
    shares = lot_size or (strat.legs[0].lot_size or 1)
    return strat.summary(spot, t_days=t_days, iv=iv, shares_per_qty=shares)


@mcp.tool()
def max_pain(symbol: str) -> dict:
    """Max pain, PCR and CE/PE walls for an underlying's live option chain.

    Fetches the public NSE snapshot in-session (may be rate-limited; retry once
    after a pause if it fails).
    """
    from .data.nse import fetch_option_chain, normalize_chain, summary_stats

    raw = fetch_option_chain(symbol)
    rows = normalize_chain(raw)
    out = {"symbol": symbol.upper(), "strikes": len(rows), **summary_stats(rows)}
    expiries = sorted({r["expiry"] for r in rows if r.get("expiry")})
    out["expiries"] = expiries[:6]
    return out


@mcp.tool()
def option_chain(symbol: str, expiry: str | None = None, atm_band: int = 5) -> dict:
    """Live NSE option chain (LTP/OI/IV) around ATM for one underlying.

    Args:
        symbol: NSE symbol, e.g. 'NIFTY', 'BANKNIFTY', 'CANBK', 'ULTRACEMCO'
        expiry: filter, e.g. '27-Oct-2026' (defaults to nearest expiry)
        atm_band: how many strikes either side of the money to return
    """
    from .data.nse import fetch_option_chain, normalize_chain, summary_stats

    raw = fetch_option_chain(symbol)
    rows = normalize_chain(raw)
    if not rows:
        return {"error": "empty chain returned by NSE"}
    expiries = sorted({r["expiry"] for r in rows if r.get("expiry")})
    if expiry is None:
        expiry = expiries[0]
    rows = [r for r in rows if r["expiry"] == expiry]
    if not rows:
        return {"error": f"no rows for expiry {expiry}", "available": expiries}

    spot = (raw.get("records") or {}).get("underlyingValue")
    if spot is None:  # fall back: strike nearest to call/put parity midpoint
        spot = min(rows, key=lambda r: abs((r["ce"]["ltp"] or 0) - (r["pe"]["ltp"] or 0)))["strike"]
    strikes = sorted({r["strike"] for r in rows})
    atm = min(strikes, key=lambda k: abs(k - spot))
    lo, hi = atm - 100 * atm_band, atm + 100 * atm_band
    band = [r for r in rows if lo <= r["strike"] <= hi]
    lot = LOT_SIZES_HINT.get(symbol.upper())
    for r in band:
        for side in ("ce", "pe"):
            oi = r[side]["oi"]
            if oi is not None:
                r[side]["oi_contracts"] = round(oi / lot) if lot else oi
    return {
        "symbol": symbol.upper(),
        "spot": spot,
        "expiry": expiry,
        "expiries": expiries[:6],
        "lot_size_hint": lot,
        "stats": summary_stats(rows),
        "chain": band,
        "disclaimer": "public NSE snapshot; estimates only, not investment advice",
    }


@mcp.tool()
def analyze_position(
    symbol: str,
    right: str,
    strike: float,
    entry: float,
    spot: float,
    t_days: float,
    qty_shares: int,
    vwap: float | None = None,
    iv: float | None = None,
) -> dict:
    """Score an open long option position: breakeven, current P&L, hold/exit framing.

    Args:
        symbol: underlying symbol (for reporting)
        right: 'C' or 'P'
        strike: strike held
        entry: entry premium per share
        spot: current underlying price
        t_days: calendar days to expiry
        qty_shares: total shares (qty * lot_size), e.g. 6750 for 1 CANBK lot
        vwap: today's VWAP if known — adds the hold-above/exit-below filter
        iv: annualized IV; if omitted, estimated 0.28 (India F&O typical) — pass a real one when known
    """
    right = right.upper()
    iv = iv if iv is not None else 0.28
    _ltp_model, g = black_scholes(spot, strike, t_days, iv, right)
    breakeven = strike + entry if right == "C" else strike - entry
    current = g.price
    cost = entry * qty_shares
    value = current * qty_shares
    out = {
        "position": f"{symbol} {strike}{right} x{qty_shares}",
        "entry": entry,
        "model_fair_value": current,
        "iv_assumed": iv,
        "pnl_rupees": round(value - cost),
        "expiry_breakeven_spot": round(breakeven, 2),
        "spot_move_needed_pct": round((breakeven / spot - 1) * 100, 2),
        "prob_profit": risk_neutral_prob(spot, breakeven, t_days, iv)
        if right == "C"
        else round(1 - risk_neutral_prob(spot, breakeven, t_days, iv), 4),
        "prob_ITM": risk_neutral_prob(spot, strike, t_days, iv)
        if right == "C"
        else round(1 - risk_neutral_prob(spot, strike, t_days, iv), 4),
        "delta": g.delta,
        "theta_per_day": g.theta,
        "expected_move_1sigma": list(expected_move(spot, t_days, iv)),
    }
    if vwap is not None:
        out["vwap_filter"] = {
            "spot": spot,
            "vwap": vwap,
            "regime": "ABOVE VWAP (hold-bias)" if spot >= vwap else "BELOW VWAP (exit-bias)",
        }
    out["disclaimer"] = "risk-neutral model estimates; not investment advice"
    return out


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
