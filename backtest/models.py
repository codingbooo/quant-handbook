"""Market data and order lifecycle value objects."""
from dataclasses import dataclass
from datetime import date
from enum import Enum
from math import isfinite


class Side(str, Enum):
    BUY = 'buy'
    SELL = 'sell'


class OrderType(str, Enum):
    MARKET = 'market'
    STOP = 'stop'


class OrderStatus(str, Enum):
    PENDING = 'pending'
    FILLED = 'filled'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'


@dataclass(frozen=True)
class Bar:
    """Daily OHLCV; explicit limits describe this session's allowed prices."""
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    symbol: str = 'SYNTH'
    limit_up: float | None = None
    limit_down: float | None = None

    def __post_init__(self) -> None:
        if not all(isfinite(p) and p > 0 for p in (self.open, self.high, self.low, self.close)):
            raise ValueError('OHLC prices must be finite and positive')
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError('inconsistent OHLC range')
        if not isinstance(self.volume, int) or self.volume < 0 or not self.symbol:
            raise ValueError('invalid volume or symbol')
        for limit in (self.limit_up, self.limit_down):
            if limit is not None and (not isfinite(limit) or limit <= 0):
                raise ValueError('limits must be finite and positive')
        if self.limit_up is not None and self.high > self.limit_up + 1e-8:
            raise ValueError('high exceeds limit up')
        if self.limit_down is not None and self.low < self.limit_down - 1e-8:
            raise ValueError('low below limit down')


@dataclass
class Order:
    """All-or-none daily order. A triggered stop executes as a market order."""
    symbol: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    stop_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    reason: str = ''
    fill_price: float | None = None
    commission: float = 0.0
    filled_at: date | None = None

    def __post_init__(self) -> None:
        self.side = Side(self.side)
        self.order_type = OrderType(self.order_type)
        if not self.symbol or not isinstance(self.quantity, int) or isinstance(self.quantity, bool) or self.quantity <= 0:
            raise ValueError('quantity must be a positive integer and symbol nonempty')
        if self.order_type == OrderType.STOP and (self.stop_price is None or not isfinite(self.stop_price) or self.stop_price <= 0):
            raise ValueError('stop orders need a positive finite stop price')


@dataclass(frozen=True)
class Trade:
    """A realized sell execution, net of allocated entry and exit commissions."""
    date: date
    symbol: str
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float
