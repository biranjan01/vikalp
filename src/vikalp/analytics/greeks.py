"""Black-Scholes pricing, greeks, IV solving and risk-neutral probabilities.

Stdlib-only on purpose: the analytics core must run anywhere, including inside
tests and constrained environments, without native dependencies.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

R_DEFAULT = 0.06  # risk-free rate assumption used across Indian retail tooling


def _ncdf(x: float) -> float:
    """Standard normal CDF via Abramowitz & Stegun 7.1.26 (|err| < 7.5e-8)."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


@dataclass
class Greeks:
    price: float
    delta: float
    gamma: float
    theta: float  # per day (calendar)
    vega: float  # per 1 vol point (1%)
    rho: float  # per 1% rate
    iv: float

    def as_dict(self) -> dict:
        return asdict(self)


def _d1_d2(spot: float, strike: float, t_years: float, iv: float, r: float):
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t_years) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t
    return d1, d2


def black_scholes(
    spot: float,
    strike: float,
    t_days: float,
    iv: float,
    right: str = "C",
    r: float = R_DEFAULT,
) -> tuple[float, Greeks]:
    """Price + greeks. ``right`` is 'C' or 'P'. ``t_days`` is calendar days to expiry."""
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if t_days < 0:
        raise ValueError("t_days must be >= 0")
    if iv < 0:
        raise ValueError("iv must be >= 0")

    right = right.upper()
    if t_days == 0 or iv == 0:  # intrinsic fallback
        intrinsic = max(spot - strike, 0.0) if right == "C" else max(strike - spot, 0.0)
        return intrinsic, Greeks(intrinsic, 0.0, 0.0, 0.0, 0.0, 0.0, iv)

    t = t_days / 365.0
    d1, d2 = _d1_d2(spot, strike, t, iv, r)
    disc = math.exp(-r * t)

    if right == "C":
        price = spot * _ncdf(d1) - strike * disc * _ncdf(d2)
        delta = _ncdf(d1)
        rho = strike * t * disc * _ncdf(d2) / 100.0
    elif right == "P":
        price = strike * disc * _ncdf(-d2) - spot * _ncdf(-d1)
        delta = _ncdf(d1) - 1.0
        rho = -strike * t * disc * _ncdf(-d2) / 100.0
    else:
        raise ValueError("right must be 'C' or 'P'")

    gamma = _npdf(d1) / (spot * iv * math.sqrt(t))
    vega = spot * _npdf(d1) * math.sqrt(t) / 100.0  # per 1 vol point
    theta = (
        -(spot * _npdf(d1) * iv) / (2.0 * math.sqrt(t))
        + (r * strike * disc * _ncdf(d2 if right == "C" else -d2)) * (-1.0 if right == "C" else 1.0)
    ) / 365.0  # per calendar day

    return price, Greeks(
        round(price, 4),
        round(delta, 6),
        round(gamma, 6),
        round(theta, 4),
        round(vega, 4),
        round(rho, 4),
        iv,
    )


def implied_vol(
    market_price: float,
    spot: float,
    strike: float,
    t_days: float,
    right: str = "C",
    r: float = R_DEFAULT,
    lo: float = 0.005,
    hi: float = 3.0,
    tol: float = 1e-4,
    max_iter: int = 200,
) -> float | None:
    """Solve IV by bisection. Returns None if no solution in [lo, hi]."""
    if market_price <= 0 or t_days <= 0:
        return None

    def model(iv: float) -> float:
        return black_scholes(spot, strike, t_days, iv, right, r)[0]

    f_lo, f_hi = model(lo) - market_price, model(hi) - market_price
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = model(mid) - market_price
        if abs(f_mid) < tol or (hi - lo) < 1e-6:
            return round(mid, 4)
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return round((lo + hi) / 2.0, 4)


def risk_neutral_prob(
    spot: float, barrier: float, t_days: float, iv: float, r: float = R_DEFAULT
) -> float:
    """P(S_T > barrier) under the risk-neutral measure. Estimates only."""
    if t_days <= 0:
        return 1.0 if spot > barrier else 0.0
    t = t_days / 365.0
    z = (math.log(spot / barrier) + (r - 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
    return round(_ncdf(z), 4)


def expected_move(spot: float, t_days: float, iv: float) -> tuple[float, float]:
    """1-sigma expected move band by expiry: (low, high)."""
    width = spot * iv * math.sqrt(t_days / 365.0)
    return round(spot - width, 2), round(spot + width, 2)
