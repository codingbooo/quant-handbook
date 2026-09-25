"""Synthetic market data generator with regime dynamics and trading constraints.

NOTE: Illustrative Simulation Model
-----------------------------------
All market dynamics, regime parameters (bull/bear/oscillating), price limit
enforcement (illustrative default 10%), and 100-share lot volume modeling in this
module are illustrative assumptions designed strictly for backtest simulation,
algorithmic strategy testing, and educational exercises. They do not represent
or claim compliance with actual exchange rules, execution microstructure, or
real-world market forecasts.

Features:
---------
1. Regimes:
   - Bull: Positive drift, moderate volatility, elevated volume on up-moves.
   - Bear: Negative drift, higher volatility, elevated volume on sharp moves.
   - Oscillating: Mean-reverting drift anchored around the initial price.
2. Illustrative Market Constraints:
   - Configurable daily price limits (default 10%, strictly 0 < limit < 1 or None).
   - Price limit bounds strictly constrain Open, High, Low, and Close.
   - Prices rounded to 2 decimal places with minimum price >= 0.01.
   - Weekday trading dates (Monday to Friday; weekends skipped).
   - Lot-friendly trading volumes (integer multiples of 100 shares).
3. Reproducibility:
   - Configurable integer seed via an isolated random.Random instance.
"""

from __future__ import annotations

import datetime
from enum import Enum
import math
import random
from types import EllipsisType

from .models import Bar


class MarketRegime(str, Enum):
    """Market regime types for synthetic data generation (illustrative)."""

    BULL = "bull"
    BEAR = "bear"
    OSCILLATING = "oscillating"


def _next_weekday(d: datetime.date) -> datetime.date:
    """Return the next weekday (skipping Saturday and Sunday)."""
    next_d = d + datetime.timedelta(days=1)
    while next_d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        next_d += datetime.timedelta(days=1)
    return next_d


def _clamp(val: float, low: float | None, high: float | None) -> float:
    """Clamp a value within [low, high] bounds if bounds are specified."""
    if low is not None and val < low:
        return low
    if high is not None and val > high:
        return high
    return val


def _validate_daily_limit_pct(limit_pct: float | None) -> None:
    """Validate daily limit percentage."""
    if limit_pct is not None:
        if (
            not isinstance(limit_pct, (int, float))
            or isinstance(limit_pct, bool)
            or not math.isfinite(limit_pct)
            or not (0.0 < limit_pct < 1.0)
        ):
            raise ValueError(f"daily_limit_pct must be a finite number strictly between 0 and 1, got: {limit_pct}")


class SyntheticMarketGenerator:
    """Configurable synthetic market data generator.

    NOTE: All market and regime assumptions are illustrative.
    """

    def __init__(
        self,
        seed: int | None = None,
        symbol: str = "SYNTH",
        daily_limit_pct: float | None = 0.10,
        base_volume: int = 1_000_000,
    ) -> None:
        if not symbol or not isinstance(symbol, str):
            raise ValueError("symbol must be a non-empty string")

        if not isinstance(base_volume, int) or isinstance(base_volume, bool) or base_volume <= 0:
            raise ValueError(f"base_volume must be a positive integer, got: {base_volume}")

        _validate_daily_limit_pct(daily_limit_pct)

        self.seed = seed
        self.symbol = symbol
        self.daily_limit_pct = daily_limit_pct
        self.base_volume = base_volume
        self._rng = random.Random(seed)

    def reseed(self, seed: int | None) -> None:
        """Reset the random number generator seed."""
        self.seed = seed
        self._rng = random.Random(seed)

    def generate(
        self,
        num_bars: int = 252,
        start_date: datetime.date | str = datetime.date(2023, 1, 3),
        regime: MarketRegime | str = MarketRegime.BULL,
        initial_price: float = 100.0,
        daily_limit_pct: float | None | EllipsisType = ...,
        volatility: float | None = None,
        drift: float | None = None,
    ) -> list[Bar]:
        """Generate a sequence of synthetic OHLCV Bar objects.

        Args:
            num_bars: Non-negative integer number of trading days to simulate.
            start_date: Start date (date or 'YYYY-MM-DD'). Advanced to weekday if weekend.
            regime: 'bull', 'bear', or 'oscillating'.
            initial_price: Initial baseline price (finite float >= 0.01).
            daily_limit_pct: Daily limit fraction (0 < limit < 1) or None.
            volatility: Daily price volatility (finite float >= 0).
            drift: Daily drift rate (finite float).

        Returns:
            List of Bar objects adhering to market constraints.
        """
        # Validate num_bars
        if not isinstance(num_bars, int) or isinstance(num_bars, bool) or num_bars < 0:
            raise ValueError(f"num_bars must be a non-negative integer, got: {num_bars}")

        if num_bars == 0:
            return []

        # Validate start_date
        if isinstance(start_date, str):
            curr_date = datetime.date.fromisoformat(start_date)
        elif isinstance(start_date, datetime.date):
            curr_date = start_date
        else:
            raise TypeError(f"start_date must be a datetime.date or ISO date string, got: {type(start_date)}")

        while curr_date.weekday() >= 5:
            curr_date += datetime.timedelta(days=1)

        # Validate initial_price
        if (
            not isinstance(initial_price, (int, float))
            or isinstance(initial_price, bool)
            or not math.isfinite(initial_price)
            or initial_price < 0.01
        ):
            raise ValueError(f"initial_price must be a finite number >= 0.01, got: {initial_price}")

        # Validate daily_limit_pct
        limit_pct = self.daily_limit_pct if daily_limit_pct is ... else daily_limit_pct
        _validate_daily_limit_pct(limit_pct)

        # Validate volatility
        if volatility is not None:
            if (
                not isinstance(volatility, (int, float))
                or isinstance(volatility, bool)
                or not math.isfinite(volatility)
                or volatility < 0
            ):
                raise ValueError(f"volatility must be a finite number >= 0, got: {volatility}")

        # Validate drift
        if drift is not None:
            if (
                not isinstance(drift, (int, float))
                or isinstance(drift, bool)
                or not math.isfinite(drift)
            ):
                raise ValueError(f"drift must be a finite number, got: {drift}")

        if isinstance(regime, str):
            regime = MarketRegime(regime.lower())

        # Regime parameters (illustrative defaults)
        if regime == MarketRegime.BULL:
            default_drift = 0.0012
            default_vol = 0.016
        elif regime == MarketRegime.BEAR:
            default_drift = -0.0010
            default_vol = 0.022
        else:  # OSCILLATING
            default_drift = 0.0
            default_vol = 0.018

        effective_drift = drift if drift is not None else default_drift
        effective_vol = volatility if volatility is not None else default_vol

        anchor_price = float(initial_price)
        prev_close = float(initial_price)

        bars: list[Bar] = []

        for _ in range(num_bars):
            # Calculate price limits based on previous close
            if limit_pct is not None:
                limit_up = round(prev_close * (1.0 + limit_pct), 2)
                limit_down = round(prev_close * (1.0 - limit_pct), 2)
                limit_down = max(0.01, limit_down)
                if limit_up < limit_down:
                    limit_up = limit_down
            else:
                limit_up = None
                limit_down = None

            # Calculate day's drift shock
            if regime == MarketRegime.OSCILLATING and drift is None:
                reversion_speed = 0.06
                distance_pct = (prev_close - anchor_price) / anchor_price
                day_drift = -reversion_speed * distance_pct
            else:
                day_drift = effective_drift

            # Sample daily return
            shock = self._rng.gauss(day_drift, effective_vol) if effective_vol > 0 else day_drift
            unconstrained_close = prev_close * (1.0 + shock)
            close_price = round(_clamp(unconstrained_close, limit_down, limit_up), 2)
            close_price = max(0.01, close_price)

            # Sample open price
            open_shock = self._rng.gauss(day_drift * 0.2, effective_vol * 0.4) if effective_vol > 0 else 0.0
            unconstrained_open = prev_close * (1.0 + open_shock)
            open_price = round(_clamp(unconstrained_open, limit_down, limit_up), 2)
            open_price = max(0.01, open_price)

            # Sample intraday high and low excursions
            body_high = max(open_price, close_price)
            body_low = min(open_price, close_price)

            high_range = (
                abs(self._rng.gauss(0, effective_vol * 0.5)) * prev_close
                if effective_vol > 0
                else 0.0
            )
            tentative_high = round(body_high + high_range, 2)
            high_price = round(_clamp(tentative_high, body_high, limit_up), 2)
            if high_price < body_high:
                high_price = body_high

            low_range = (
                abs(self._rng.gauss(0, effective_vol * 0.5)) * prev_close
                if effective_vol > 0
                else 0.0
            )
            tentative_low = round(body_low - low_range, 2)
            low_price = round(_clamp(tentative_low, limit_down, body_low), 2)
            low_price = max(0.01, low_price)
            if low_price > body_low:
                low_price = body_low

            # Enforce strict OHLC ordering consistency
            if high_price < body_high:
                high_price = body_high
            if low_price > body_low:
                low_price = body_low

            # Lot-friendly volume: multiple of 100 shares
            price_change_pct = abs(close_price - prev_close) / prev_close
            vol_multiplier = 1.0 + 3.0 * price_change_pct
            if close_price > prev_close:
                vol_multiplier *= 1.15
            noise = self._rng.lognormvariate(0.0, 0.25)
            raw_volume = self.base_volume * vol_multiplier * noise
            volume = max(100, int(round(raw_volume / 100.0)) * 100)

            bar = Bar(
                date=curr_date,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                symbol=self.symbol,
                limit_up=limit_up,
                limit_down=limit_down,
            )
            bars.append(bar)

            curr_date = _next_weekday(curr_date)
            prev_close = close_price

        return bars


def generate_market_data(
    num_bars: int = 252,
    start_date: datetime.date | str = datetime.date(2023, 1, 3),
    regime: MarketRegime | str = MarketRegime.BULL,
    initial_price: float = 100.0,
    daily_limit_pct: float | None = 0.10,
    seed: int | None = None,
    symbol: str = "SYNTH",
    base_volume: int = 1_000_000,
    volatility: float | None = None,
    drift: float | None = None,
) -> list[Bar]:
    """Generate synthetic market OHLCV bars.

    NOTE: Market assumptions are illustrative simulations for testing.

    Args:
        num_bars: Non-negative integer number of trading day bars to generate.
        start_date: Start date for the simulation (weekdays only).
        regime: 'bull', 'bear', or 'oscillating'.
        initial_price: Starting baseline price (finite float >= 0.01).
        daily_limit_pct: Daily price limit ratio (0 < limit < 1) or None.
        seed: Random seed for deterministic reproducibility.
        symbol: Ticker symbol string.
        base_volume: Positive int base trading volume (lot rounded to 100).
        volatility: Optional non-negative volatility override.
        drift: Optional finite drift override.

    Returns:
        List of Bar objects with illustrative market constraints.
    """
    generator = SyntheticMarketGenerator(
        seed=seed,
        symbol=symbol,
        daily_limit_pct=daily_limit_pct,
        base_volume=base_volume,
    )
    return generator.generate(
        num_bars=num_bars,
        start_date=start_date,
        regime=regime,
        initial_price=initial_price,
        daily_limit_pct=daily_limit_pct,
        volatility=volatility,
        drift=drift,
    )


generate_synthetic_bars = generate_market_data

