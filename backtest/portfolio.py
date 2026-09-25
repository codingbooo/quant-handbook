"""Long-only cash accounting with FIFO lots and optional T+1 settlement."""
from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import Mapping
from .models import Side, Trade


@dataclass
class Lot:
    quantity: int
    price: float
    entry_fee_per_share: float
    acquired: date


class Portfolio:
    """Owns inventory and realized P&L; prices include execution slippage."""

    def __init__(self, initial_cash: float = 100_000.0) -> None:
        if not isfinite(initial_cash) or initial_cash < 0:
            raise ValueError('initial cash must be finite and nonnegative')
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.positions: dict[str, list[Lot]] = {}
        self.trades: list[Trade] = []

    def quantity(self, symbol: str) -> int:
        return sum(lot.quantity for lot in self.positions.get(symbol, []))

    def available(self, symbol: str, when: date, t_plus_one: bool = True) -> int:
        return sum(lot.quantity for lot in self.positions.get(symbol, [])
                   if not t_plus_one or lot.acquired < when)

    def equity(self, prices: Mapping[str, float]) -> float:
        """Mark inventory at supplied prices; missing held symbols raise KeyError."""
        return self.cash + sum(self.quantity(s) * prices[s] for s in self.positions if self.quantity(s))

    def fill(self, symbol: str, side: Side, quantity: int, price: float,
             fee: float, when: date, t_plus_one: bool = True) -> None:
        """Apply a complete execution atomically or raise ValueError."""
        side = Side(side)
        if not isinstance(quantity, int) or quantity <= 0 or not isfinite(price) or price <= 0 or not isfinite(fee) or fee < 0:
            raise ValueError('invalid execution')
        if side == Side.BUY:
            cost = quantity * price + fee
            if cost > self.cash + 1e-9:
                raise ValueError('insufficient cash')
            self.cash = max(0.0, self.cash - cost)
            self.positions.setdefault(symbol, []).append(Lot(quantity, price, fee / quantity, when))
            return
        if quantity > self.available(symbol, when, t_plus_one):
            raise ValueError('insufficient settled position')
        if self.cash + quantity * price < fee:
            raise ValueError('insufficient cash for commission')
        remaining, basis, entry_value = quantity, 0.0, 0.0
        for lot in self.positions.get(symbol, []):
            if remaining == 0:
                break
            if t_plus_one and lot.acquired >= when:
                continue
            take = min(remaining, lot.quantity)
            basis += take * (lot.price + lot.entry_fee_per_share)
            entry_value += take * lot.price
            lot.quantity -= take
            remaining -= take
        self.positions[symbol] = [lot for lot in self.positions[symbol] if lot.quantity]
        self.cash += quantity * price - fee
        self.trades.append(Trade(when, symbol, quantity, entry_value / quantity,
                                 price, quantity * price - fee - basis))
