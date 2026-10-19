"""Multi-leg option strategy payoff engine (expiry payoffs + risk metrics)."""

from __future__ import annotations

from dataclasses import dataclass

from .greeks import risk_neutral_prob


@dataclass
class Leg:
    strike: float
    right: str  # 'C' or 'P'
    qty: int  # +N long, -N short (contracts)
    premium: float  # entry premium per share
    lot_size: int = 1  # contracts per "lot" is qty * lot_size shares total

    @classmethod
    def from_dict(cls, d: dict) -> Leg:
        return cls(
            strike=float(d["strike"]),
            right=str(d.get("right", "C")).upper(),
            qty=int(d["qty"]),
            premium=float(d["premium"]),
            lot_size=int(d.get("lot_size", 1)),
        )


def leg_intrinsic(strike: float, right: str, s: float) -> float:
    if right == "C":
        return max(s - strike, 0.0)
    if right == "P":
        return max(strike - s, 0.0)
    raise ValueError("right must be 'C' or 'P'")


class Strategy:
    def __init__(self, legs: list[dict | Leg]):
        self.legs = [l if isinstance(l, Leg) else Leg.from_dict(l) for l in legs]
        if not self.legs:
            raise ValueError("strategy needs at least one leg")
        for l in self.legs:
            if l.right not in ("C", "P"):
                raise ValueError("leg.right must be 'C' or 'P'")

    @property
    def net_debit(self) -> float:
        """Net premium paid per share (positive = debit, negative = credit)."""
        return sum(l.premium * l.qty for l in self.legs)

    def payoff_at(self, s: float) -> float:
        """P&L per share at expiry for underlying price ``s``."""
        intrinsic = sum(l.qty * leg_intrinsic(l.strike, l.right, s) for l in self.legs)
        return intrinsic - self.net_debit

    def pnl_rupees(self, s: float, shares_per_qty: int = 1) -> int:
        """Total P&L in ₹: payoff * qty-shares. shares_per_qty = option lot size."""
        return round(self.payoff_at(s) * shares_per_qty)

    def curve(self, s_min: float, s_max: float, steps: int = 201) -> list[tuple[float, float]]:
        if steps < 2:
            raise ValueError("steps must be >= 2")
        step = (s_max - s_min) / (steps - 1)
        return [
            (round(s_min + i * step, 2), round(self.payoff_at(s_min + i * step), 2))
            for i in range(steps)
        ]

    def breakevens(self, s_min: float, s_max: float, steps: int = 4001) -> list[float]:
        """Find zero-crossings of the payoff by dense scan + linear interpolation."""
        out: list[float] = []
        prev_s, prev_p = s_min, self.payoff_at(s_min)
        step = (s_max - s_min) / (steps - 1)
        for i in range(1, steps):
            s = s_min + i * step
            p = self.payoff_at(s)
            if prev_p == 0.0:
                out.append(round(prev_s, 2))
            elif prev_p * p < 0:
                frac = abs(prev_p) / (abs(prev_p) + abs(p))
                out.append(round(prev_s + frac * step, 2))
            prev_s, prev_p = s, p
        # de-dup
        dedup: list[float] = []
        for b in out:
            if not dedup or abs(b - dedup[-1]) > 1e-6:
                dedup.append(b)
        return dedup

    def max_loss(self, s_min: float = 0.0, s_max: float = 10_000_000.0) -> float:
        """Worst-case payoff per share over the scanned range."""
        pts = self.curve(s_min, s_max, 2001)
        return min(p for _, p in pts)

    def max_profit(self, s_min: float = 0.0, s_max: float = 10_000_000.0) -> float:
        pts = self.curve(s_min, s_max, 2001)
        return max(p for _, p in pts)

    def prob_profit(self, spot: float, t_days: float, iv: float) -> float:
        """Risk-neutral P(strategy in profit) — approximation for single-ish structures.

        Uses the probability of finishing above the highest long-call breakeven
        (or below the lowest long-put breakeven); for mixed structures this is a
        rough estimate, clearly flagged as such in output.
        """
        bes = self.breakevens(
            min(l.strike for l in self.legs) * 0.5, max(l.strike for l in self.legs) * 1.5
        )
        if not bes:
            return 0.5
        has_long_call = any(l.qty > 0 and l.right == "C" for l in self.legs)
        target = max(bes) if has_long_call else min(bes)
        if has_long_call:
            return risk_neutral_prob(spot, target, t_days, iv)
        # long put side: P(S_T < breakeven)
        return round(1.0 - risk_neutral_prob(spot, target, t_days, iv), 4)

    def summary(
        self, spot: float, t_days: float = 8, iv: float = 0.20, shares_per_qty: int = 1
    ) -> dict:
        lo = min(l.strike for l in self.legs) * 0.6
        hi = max(l.strike for l in self.legs) * 1.6
        bes = self.breakevens(lo, hi)
        return {
            "spot": spot,
            "net_debit_per_share": round(self.net_debit, 2),
            "net_debit_rupees": round(self.net_debit * shares_per_qty),
            "breakevens": bes,
            "max_loss_per_share": round(self.max_loss(lo, hi), 2),
            "max_profit_per_share": round(self.max_profit(lo, hi), 2),
            "payoff_now": round(self.payoff_at(spot), 2),
            "pnl_if_flat_rupees": self.pnl_rupees(spot, shares_per_qty),
            "prob_profit_est": self.prob_profit(spot, t_days, iv),
            "disclaimer": "risk-neutral estimate; not investment advice",
        }
