<div align="center">

# Vikalp

**Open-source options lab for Indian markets — with an AI agent built in.**

`option chains · greeks · strategy payoff · max pain · position analyzer · MCP server`

[![CI](https://img.shields.io/badge/CI-TODO-blue)](#) [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE) [![Python](https://img.shields.io/badge/python-3.10+-blue)](#)

</div>

> **Vikalp** (विकल्प, *"option"*) is a free, open-source alternative to Sensibull / Opstra for
> NSE & BSE options — usable from the terminal, from Python, or **directly inside your AI
> coding agent** (Claude Code, OpenCode, Cursor, Gemini CLI, any MCP client).

```
You:  "Analyze my CANBK 121 CE position — should I hold above VWAP?"
AI:   (calls vikalp MCP tools → chain, OI, greeks, payoff)
      "Hold while spot > 121.70, exit below 121.00. Breakeven 123.78 needs +1.6%..."
```

## Why

Every serious options tool in India — Sensibull, Opstra, Quantsapp, AlgoTest — is a paid
walled garden. Meanwhile AI agents can't touch market data at all. Vikalp fixes both:

- **100% open source (MIT)** — no subscription, no walled garden, your data stays yours
- **Bring your own broker** — works with Kite Connect, Upstox, Fyers, Dhan, or free NSE snapshots
- **MCP-native** — one config line gives *your* agent option chains, greeks and payoff math

## Quickstart

```bash
pip install vikalp
```

### Use from your AI agent (MCP)

```json
{
  "mcpServers": {
    "vikalp": { "command": "vikalp-mcp" }
  }
}
```

Works in Claude Code, OpenCode, Cursor, Gemini CLI — any client that speaks MCP.

### Use from Python

```python
from vikalp.analytics.greeks import black_scholes, implied_vol
from vikalp.analytics.strategy import Strategy

# Single-leg fair value + greeks
price, g = black_scholes(spot=121.77, strike=121, t_days=8, iv=0.26, right="C")

# Multi-leg payoff: bull call spread
s = Strategy([
    {"strike": 121, "right": "C", "qty": 1, "premium": 2.78},
    {"strike": 125, "right": "C", "qty": -1, "premium": 0.90},
])
print(s.summary(spot=121.77))
```

## MCP tools

| Tool | What it does |
|---|---|
| `option_chain` | Live NSE option chain (LTP, OI, IV, volume) for any F&O underlying |
| `greeks` | Solve implied volatility from a market price, then full greeks + probabilities |
| `strategy_payoff` | Multi-leg payoff: breakevens, max loss/profit, risk-neutral P(profit) |
| `max_pain` | Max-pain strike + call/put walls for an expiry |
| `analyze_position` | Score an open option position: breakeven, VWAP filter, hold/exit levels |

## Roadmap

- [x] Core analytics engine (BS greeks, IV solver, payoff engine, max pain)
- [x] MCP server with 5 tools
- [ ] Live data connectors: NSE snapshot, Upstox, Kite (bring-your-own key)
- [ ] Position analyzer with intraday OI build-up classification
- [ ] Web dashboard (chains, strategy builder, payoff charts)
- [ ] Option-strategy backtester (event studies: expiry → expiry)
- [ ] Hindi + English docs

## Data & compliance

- Market data is fetched **live in your session** from your own broker API keys or public
  NSE endpoints — Vikalp redistributes no exchange data.
- NSE/BSE data is subject to exchange terms; use broker APIs for anything beyond personal use.

## Disclaimer

Vikalp is an analysis tool, **not investment advice**. Options trading involves substantial
risk of loss. Model outputs (greeks, probabilities) are estimates. Consult a registered
advisor before trading.

## License

[MIT](LICENSE)
