"""Quantitative trading strategies for event-driven daily backtesting."""
from collections.abc import Sequence
from math import isfinite
from .models import Bar, Order, OrderType, Side
from .portfolio import Portfolio


class DualSMAStrategy:
    """Dual Simple Moving Average (SMA) crossover strategy with volume confirmation.

    Signals:
    - Long Entry: Bullish crossover (fast SMA crosses strictly above slow SMA)
      confirmed by volume (current bar volume >= vol_multiplier * volume SMA),
      submitting a next-bar MARKET BUY order for 'quantity' shares if currently flat.
    - Exit: Bearish crossover (fast SMA crosses strictly below slow SMA),
      submitting a next-bar MARKET SELL order for all currently held shares.
    - Latching Exit: If an exit sell order cannot execute (e.g. locked limit-down),
      retains an _exit_pending latch and retries every subsequent bar until flat.
    """

    def __init__(
        self,
        fast_period: int = 5,
        slow_period: int = 20,
        vol_period: int = 20,
        vol_multiplier: float = 1.0,
        quantity: int = 100,
        lot_size: int = 100,
    ) -> None:
        if not isinstance(fast_period, int) or fast_period <= 0:
            raise ValueError("fast_period must be a positive integer")
        if not isinstance(slow_period, int) or slow_period <= 0:
            raise ValueError("slow_period must be a positive integer")
        if fast_period >= slow_period:
            raise ValueError("slow_period must be strictly greater than fast_period")
        if not isinstance(vol_period, int) or vol_period <= 0:
            raise ValueError("vol_period must be a positive integer")
        if not isinstance(vol_multiplier, (int, float)) or not isfinite(vol_multiplier) or vol_multiplier < 0:
            raise ValueError("vol_multiplier must be a finite nonnegative number")
        if not isinstance(lot_size, int) or lot_size <= 0:
            raise ValueError("lot_size must be a positive integer")
        if not isinstance(quantity, int) or quantity <= 0 or quantity % lot_size != 0:
            raise ValueError("quantity must be a positive integer multiple of lot_size")

        self.fast_period = fast_period
        self.slow_period = slow_period
        self.vol_period = vol_period
        self.vol_multiplier = float(vol_multiplier)
        self.quantity = quantity
        self.lot_size = lot_size
        self._exit_pending = False

    def on_bar(self, history: Sequence[Bar], portfolio: Portfolio) -> list[Order]:
        """Generate orders based on SMA crossover and volume confirmation."""
        min_bars = max(self.slow_period, self.vol_period) + 1
        if len(history) < min_bars:
            return []

        symbol = history[-1].symbol
        pos = portfolio.quantity(symbol)

        if pos == 0:
            self._exit_pending = False

        # Retry pending exit if previous exit was blocked
        if pos > 0 and self._exit_pending:
            return [Order(symbol=symbol, side=Side.SELL, quantity=pos, order_type=OrderType.MARKET)]

        curr_fast = sum(b.close for b in history[-self.fast_period:]) / self.fast_period
        prev_fast = sum(b.close for b in history[-self.fast_period - 1 : -1]) / self.fast_period
        curr_slow = sum(b.close for b in history[-self.slow_period:]) / self.slow_period
        prev_slow = sum(b.close for b in history[-self.slow_period - 1 : -1]) / self.slow_period

        vol_ma = sum(b.volume for b in history[-self.vol_period:]) / self.vol_period
        vol_confirmed = history[-1].volume >= vol_ma * self.vol_multiplier

        # Bearish death cross
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            if pos > 0:
                self._exit_pending = True
                return [Order(symbol=symbol, side=Side.SELL, quantity=pos, order_type=OrderType.MARKET)]

        # Bullish golden cross
        if prev_fast <= prev_slow and curr_fast > curr_slow and vol_confirmed:
            if pos == 0 and not self._exit_pending:
                return [Order(symbol=symbol, side=Side.BUY, quantity=self.quantity, order_type=OrderType.MARKET)]

        return []


class DynamicGridStrategy:
    """Dynamic grid strategy with floor/ceiling boundaries and trailing exit.

    Mechanics:
    - Generates grid levels spaced by 'grid_step' between 'floor_price' and 'ceiling_price'.
    - Downward crossing generates next-bar MARKET BUY orders unless at/above ceiling or at/below floor.
    - Upward crossing generates next-bar MARKET SELL orders capped at held quantity (no shorting).
    - Hard floor exit (close <= floor_price) submits a next-bar MARKET SELL for all shares.
    - Trailing stop exit (close <= highest_price * (1 - trailing_stop_pct)) submits a next-bar MARKET SELL.
    - Daily reissuance of protective STOP order at max(floor_price, trailing_stop) for held shares.
    - Preserves tracking state until positions are actually closed (pos == 0), retrying blocked exits.
    """

    MAX_GRID_LEVELS = 10_000

    def __init__(
        self,
        floor_price: float,
        ceiling_price: float,
        grid_step: float,
        trailing_stop_pct: float = 0.05,
        quantity: int = 100,
        lot_size: int = 100,
        base_price: float | None = None,
    ) -> None:
        if not isinstance(floor_price, (int, float)) or not isfinite(floor_price) or floor_price <= 0:
            raise ValueError("floor_price must be a positive finite number")
        if not isinstance(ceiling_price, (int, float)) or not isfinite(ceiling_price) or ceiling_price <= floor_price:
            raise ValueError("ceiling_price must be finite and strictly greater than floor_price")
        if not isinstance(grid_step, (int, float)) or not isfinite(grid_step) or grid_step <= 0:
            raise ValueError("grid_step must be a positive finite number")
        if float(floor_price) + float(grid_step) <= float(floor_price):
            raise ValueError("grid_step is too small to advance beyond floor_price")
        if (float(ceiling_price) - float(floor_price)) / float(grid_step) > self.MAX_GRID_LEVELS:
            raise ValueError(f"grid_step produces excessive grid levels (> {self.MAX_GRID_LEVELS})")
        if not isinstance(trailing_stop_pct, (int, float)) or not isfinite(trailing_stop_pct) or not 0 < trailing_stop_pct < 1:
            raise ValueError("trailing_stop_pct must be a number in (0, 1)")
        if not isinstance(lot_size, int) or lot_size <= 0:
            raise ValueError("lot_size must be a positive integer")
        if not isinstance(quantity, int) or quantity <= 0 or quantity % lot_size != 0:
            raise ValueError("quantity must be a positive integer multiple of lot_size")
        if base_price is not None:
            if not isinstance(base_price, (int, float)) or not isfinite(base_price) or not (floor_price <= base_price <= ceiling_price):
                raise ValueError("base_price must lie within [floor_price, ceiling_price]")

        self.floor_price = float(floor_price)
        self.ceiling_price = float(ceiling_price)
        self.grid_step = float(grid_step)
        self.trailing_stop_pct = float(trailing_stop_pct)
        self.quantity = quantity
        self.lot_size = lot_size
        self.base_price = float(base_price) if base_price is not None else None

        self._highest_price = 0.0
        self._exiting = False
        self.levels = self._generate_levels()

    def _generate_levels(self) -> list[float]:
        levels: list[float] = []
        if self.base_price is not None:
            p = self.base_price - self.grid_step
            while p > self.floor_price + 1e-8:
                levels.append(round(p, 8))
                p -= self.grid_step
            p = self.base_price
            while p < self.ceiling_price - 1e-8:
                if p > self.floor_price + 1e-8:
                    levels.append(round(p, 8))
                p += self.grid_step
        else:
            p = self.floor_price + self.grid_step
            while p < self.ceiling_price - 1e-8:
                levels.append(round(p, 8))
                p += self.grid_step
        return sorted(set(levels))

    def on_bar(self, history: Sequence[Bar], portfolio: Portfolio) -> list[Order]:
        """Generate grid orders and maintain protective stops."""
        if not history:
            return []

        curr_bar = history[-1]
        symbol = curr_bar.symbol
        pos = portfolio.quantity(symbol)

        if pos == 0:
            self._exiting = False
            self._highest_price = 0.0
        elif not self._exiting:
            self._highest_price = max(self._highest_price, curr_bar.high, curr_bar.close)

        trailing_stop = self._highest_price * (1.0 - self.trailing_stop_pct) if self._highest_price > 0 else 0.0

        # Hard floor exit or trailing stop exit trigger or retry
        if pos > 0:
            if self._exiting or curr_bar.close <= self.floor_price or (trailing_stop > 0 and curr_bar.close <= trailing_stop):
                self._exiting = True
                return [Order(symbol=symbol, side=Side.SELL, quantity=pos, order_type=OrderType.MARKET)]

        orders: list[Order] = []
        sell_qty = 0

        # Level crossings require at least two bars
        if len(history) >= 2:
            prev_close = history[-2].close
            curr_close = curr_bar.close

            down_crosses = 0
            up_crosses = 0
            if prev_close > curr_close:
                down_crosses = sum(1 for lvl in self.levels if prev_close > lvl >= curr_close)
            elif curr_close > prev_close:
                up_crosses = sum(1 for lvl in self.levels if prev_close < lvl <= curr_close)

            # Upward crossing -> Sell
            if up_crosses > 0 and pos > 0:
                sell_qty = min(pos, self.quantity * up_crosses)
                if sell_qty > 0:
                    orders.append(Order(symbol=symbol, side=Side.SELL, quantity=sell_qty, order_type=OrderType.MARKET))

            # Downward crossing -> Buy (ceiling: no new buys)
            if down_crosses > 0 and curr_close < self.ceiling_price and curr_close > self.floor_price:
                buy_qty = self.quantity * down_crosses
                orders.append(Order(symbol=symbol, side=Side.BUY, quantity=buy_qty, order_type=OrderType.MARKET))

        # Reissue protective stop each day for remaining held position
        remaining_pos = pos - sell_qty
        if remaining_pos > 0:
            effective_stop = max(self.floor_price, trailing_stop)
            orders.append(Order(symbol=symbol, side=Side.SELL, quantity=remaining_pos, order_type=OrderType.STOP, stop_price=round(effective_stop, 4)))

        return orders


class TrailingStopATRStrategy:
    """Average True Range (ATR) trailing stop strategy with profit locking.

    Mechanics:
    - One-shot auto-entry on warmup completion (len(history) >= atr_period + 1) with fixed 'quantity'.
      Submits a next-bar MARKET BUY order and retries across subsequent bars until the position is filled.
      Does not re-enter on subsequent exits once the initial position has been entered.
    - ATR stop never loosens: ratchets upward with highest price.
    - Profit-lock activation: once unrealized gain from entry reaches 'profit_lock_activation'
      (0.0 activates profit locking immediately on any positive profit), locks in at least
      'profit_lock_fraction' of peak profit: entry_price + profit * profit_lock_fraction.
    - Submits next-bar MARKET SELL order if close <= stop_price, else reissues
      a protective STOP order each day.
    - Preserves tracking state until positions are actually closed (pos == 0), retrying blocked exits.
    """

    def __init__(
        self,
        atr_period: int = 14,
        atr_multiplier: float = 2.0,
        profit_lock_activation: float = 0.05,
        profit_lock_fraction: float = 0.5,
        quantity: int = 100,
        lot_size: int = 100,
        auto_enter: bool = True,
    ) -> None:
        if not isinstance(atr_period, int) or atr_period <= 0:
            raise ValueError("atr_period must be a positive integer")
        if not isinstance(atr_multiplier, (int, float)) or not isfinite(atr_multiplier) or atr_multiplier <= 0:
            raise ValueError("atr_multiplier must be a positive finite number")
        if not isinstance(profit_lock_activation, (int, float)) or not isfinite(profit_lock_activation) or profit_lock_activation < 0:
            raise ValueError("profit_lock_activation must be a finite nonnegative number")
        if not isinstance(profit_lock_fraction, (int, float)) or not isfinite(profit_lock_fraction) or not (0 <= profit_lock_fraction <= 1):
            raise ValueError("profit_lock_fraction must be a number in [0, 1]")
        if not isinstance(lot_size, int) or lot_size <= 0:
            raise ValueError("lot_size must be a positive integer")
        if not isinstance(quantity, int) or quantity <= 0 or quantity % lot_size != 0:
            raise ValueError("quantity must be a positive integer multiple of lot_size")
        if not isinstance(auto_enter, bool):
            raise ValueError("auto_enter must be a boolean")

        self.atr_period = atr_period
        self.atr_multiplier = float(atr_multiplier)
        self.profit_lock_activation = float(profit_lock_activation)
        self.profit_lock_fraction = float(profit_lock_fraction)
        self.quantity = quantity
        self.lot_size = lot_size
        self.auto_enter = auto_enter

        self._entry_price = 0.0
        self._highest_price = 0.0
        self._stop_price = 0.0
        self._exiting = False
        self._warmup_entered = False

    def on_bar(self, history: Sequence[Bar], portfolio: Portfolio) -> list[Order]:
        """Compute ATR, update trailing/profit-lock stop, and generate orders."""
        if len(history) < self.atr_period + 1:
            return []

        curr_bar = history[-1]
        symbol = curr_bar.symbol
        pos = portfolio.quantity(symbol)

        # Calculate standard ATR
        tr_list: list[float] = []
        for i in range(len(history) - self.atr_period, len(history)):
            prev_c = history[i - 1].close
            bar = history[i]
            tr = max(bar.high - bar.low, abs(bar.high - prev_c), abs(bar.low - prev_c))
            tr_list.append(tr)
        atr = sum(tr_list) / self.atr_period

        # When flat, reset tracking state
        if pos == 0:
            self._entry_price = 0.0
            self._highest_price = 0.0
            self._stop_price = 0.0
            self._exiting = False
            if self.auto_enter and not self._warmup_entered:
                # Retry submitting buy order until an entry fills
                return [Order(symbol=symbol, side=Side.BUY, quantity=self.quantity, order_type=OrderType.MARKET)]
            return []

        # Position is observed filled: mark warmup entered
        self._warmup_entered = True

        # Initialize or update held position state
        if self._entry_price <= 0.0:
            lots = portfolio.positions.get(symbol)
            if lots:
                self._entry_price = lots[0].price
            else:
                self._entry_price = curr_bar.close
            self._highest_price = curr_bar.high
            self._stop_price = max(0.01, self._entry_price - self.atr_multiplier * atr)
        elif not self._exiting:
            self._highest_price = max(self._highest_price, curr_bar.high)

        candidate_stop = self._highest_price - self.atr_multiplier * atr

        # Profit locking ratchet: 0.0 activates immediately on any positive profit
        if self._entry_price > 0 and self._highest_price > self._entry_price:
            gain = (self._highest_price - self._entry_price) / self._entry_price
            if gain >= self.profit_lock_activation:
                accrued = self._highest_price - self._entry_price
                locked = self._entry_price + accrued * self.profit_lock_fraction
                candidate_stop = max(candidate_stop, locked)

        # ATR stop never loosens while position continues normally
        if not self._exiting:
            self._stop_price = max(self._stop_price, candidate_stop, 0.01)

        # Check exit breach or retry previous blocked exit
        if self._exiting or curr_bar.close <= self._stop_price:
            self._exiting = True
            return [Order(symbol=symbol, side=Side.SELL, quantity=pos, order_type=OrderType.MARKET)]

        # Reissue protective stop order for next session
        return [Order(symbol=symbol, side=Side.SELL, quantity=pos, order_type=OrderType.STOP, stop_price=round(self._stop_price, 4))]
