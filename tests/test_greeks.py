"""Core analytics tests — stdlib only, runnable without pytest:

python3 tests/test_greeks.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vikalp.analytics.greeks import (
    black_scholes,
    expected_move,
    implied_vol,
    risk_neutral_prob,
)
from vikalp.analytics.strategy import Strategy


def test_atm_call_sanity():
    price, g = black_scholes(spot=100.0, strike=100.0, t_days=30, iv=0.20, right="C")
    # textbook: ATM 30d 20%IV ≈ 2.5
    assert 2.0 < price < 3.2, price
    assert 0.45 < g.delta < 0.58, g.delta
    assert g.gamma > 0 and g.vega > 0 and g.theta < 0


def test_put_call_parity():
    spot, k, t, iv = 121.77, 121.0, 8.0, 0.26
    c, _ = black_scholes(spot, k, t, iv, "C")
    p, _ = black_scholes(spot, k, t, iv, "P")
    disc = k * math.exp(-0.06 * t / 365.0)
    assert abs((c - p) - (spot - disc)) < 0.02


def test_iv_roundtrip():
    target = 3.14159
    price, _ = black_scholes(121.77, 121.0, 8.0, 0.26, "C")
    iv = implied_vol(price, 121.77, 121.0, 8.0, "C")
    assert iv is not None and abs(iv - 0.26) < 0.001, iv
    assert target  # keep linters quiet


def test_deep_itm_delta():
    _, g = black_scholes(spot=130.0, strike=121.0, t_days=8, iv=0.26, right="C")
    assert g.delta > 0.9
    _, gp = black_scholes(spot=110.0, strike=121.0, t_days=8, iv=0.26, right="C")
    assert gp.delta < 0.1


def test_prob_and_move():
    low, high = expected_move(10_000.0, 8, 0.26)
    assert low < 10_000 < high and (high - low) > 0
    p = risk_neutral_prob(100.0, 104.0, 8, 0.26)
    assert 0.0 < p < 0.5  # barrier above spot ⇒ < 50%


def test_single_call_breakeven():
    # long 121 CE @2.78 → breakeven spot must be 123.78
    s = Strategy([{"strike": 121, "right": "C", "qty": 1, "premium": 2.78}])
    bes = s.breakevens(100, 150)
    assert len(bes) == 1 and abs(bes[0] - 123.78) < 0.05, bes
    assert abs(s.max_loss() + 2.78) < 1e-6  # lose exactly the premium
    assert s.max_profit() > 1000  # naked call: unbounded-ish on scan


def test_bull_call_spread():
    s = Strategy(
        [
            {"strike": 121, "right": "C", "qty": 1, "premium": 2.78},
            {"strike": 125, "right": "C", "qty": -1, "premium": 0.90},
        ]
    )
    assert abs(s.net_debit - 1.88) < 1e-9
    assert abs(s.max_profit() - (4.0 - 1.88)) < 0.01  # capped at width - debit
    assert abs(s.max_loss() + 1.88) < 0.01  # debit is max loss
    bes = s.breakevens(100, 150)
    assert abs(bes[0] - 122.88) < 0.05, bes


def test_summary_shape():
    s = Strategy([{"strike": 11100, "right": "C", "qty": 1, "premium": 202.45}])
    out = s.summary(spot=10_862, t_days=8, iv=0.278, shares_per_qty=50)
    assert out["net_debit_rupees"] == 10122
    assert out["breakevens"] and abs(out["breakevens"][0] - 11302.45) < 0.1
    assert 0 <= out["prob_profit_est"] <= 1


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
