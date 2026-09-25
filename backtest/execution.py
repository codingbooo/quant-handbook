"""Configurable transaction costs and conservative daily-bar execution."""
from dataclasses import dataclass
from math import isfinite
from .models import Bar, Order, OrderStatus, OrderType, Side
from .portfolio import Portfolio


@dataclass(frozen=True)
class CommissionModel:
    """Proportional broker fee with minimum, plus an optional sell-side tax."""
    rate: float = 0.0003
    minimum: float = 5.0
    sell_tax: float = 0.0

    def __post_init__(self) -> None:
        if any(not isfinite(v) or v < 0 for v in (self.rate, self.minimum, self.sell_tax)):
            raise ValueError('commission parameters must be finite and nonnegative')

    def calculate(self, side: Side, notional: float) -> float:
        return max(self.minimum, notional * self.rate) + (notional * self.sell_tax if side == Side.SELL else 0)


@dataclass(frozen=True)
class SlippageModel:
    """Adverse proportional slippage, clipped to the observed daily range."""
    rate: float = 0.0005

    def __post_init__(self) -> None:
        if not isfinite(self.rate) or not 0 <= self.rate < 1:
            raise ValueError('slippage rate must lie in [0, 1)')

    def apply(self, side: Side, price: float) -> float:
        return price * (1 + self.rate if side == Side.BUY else 1 - self.rate)


class Broker:
    """Executes all-or-none orders, with no leverage or short selling."""

    def __init__(self, commission: CommissionModel, slippage: SlippageModel,
                 lot_size: int = 100, t_plus_one: bool = True) -> None:
        if not isinstance(lot_size, int) or lot_size <= 0:
            raise ValueError('lot size must be positive')
        self.commission, self.slippage = commission, slippage
        self.lot_size, self.t_plus_one = lot_size, t_plus_one

    def execute(self, order: Order, bar: Bar, portfolio: Portfolio) -> None:
        """Untriggered or illiquid orders remain pending until engine replacement."""
        if order.status != OrderStatus.PENDING or order.symbol != bar.symbol:
            return
        if bar.volume == 0:
            order.reason = 'no volume'
            return
        locked_up = bar.limit_up is not None and bar.low >= bar.limit_up - 1e-8
        locked_down = bar.limit_down is not None and bar.high <= bar.limit_down + 1e-8
        if (order.side == Side.BUY and locked_up) or (order.side == Side.SELL and locked_down):
            order.reason = 'locked price limit'
            return
        price = bar.open
        if order.order_type == OrderType.STOP:
            stop = order.stop_price
            assert stop is not None
            if order.side == Side.SELL:
                if bar.low > stop:
                    return
                price = min(bar.open, stop)
            else:
                if bar.high < stop:
                    return
                price = max(bar.open, stop)
        if order.side == Side.BUY and order.quantity % self.lot_size:
            order.status, order.reason = OrderStatus.REJECTED, 'buy quantity must be a lot multiple'
            return
        if order.quantity > bar.volume:
            order.status, order.reason = OrderStatus.REJECTED, 'insufficient bar volume'
            return
        price = min(bar.high, max(bar.low, self.slippage.apply(order.side, price)))
        fee = self.commission.calculate(order.side, price * order.quantity)
        try:
            portfolio.fill(order.symbol, order.side, order.quantity, price, fee, bar.date, self.t_plus_one)
        except ValueError as exc:
            order.status, order.reason = OrderStatus.REJECTED, str(exc)
            return
        order.status, order.reason = OrderStatus.FILLED, ''
        order.fill_price, order.commission, order.filled_at = price, fee, bar.date
