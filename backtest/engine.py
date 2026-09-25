"""Chronological single-instrument daily backtest orchestration."""
from dataclasses import dataclass
from typing import Protocol, Sequence
from .models import Bar, Order, OrderStatus, Trade
from .portfolio import Portfolio
from .execution import Broker, CommissionModel, SlippageModel
from .metrics import calculate_metrics


class Strategy(Protocol):
    """Signals use only completed bars and execute no sooner than the next bar."""
    def on_bar(self, history: Sequence[Bar], portfolio: Portfolio) -> list[Order]: ...


@dataclass
class BacktestResult:
    portfolio: Portfolio
    orders: list[Order]
    equity_curve: list[float]
    trades: list[Trade]
    metrics: dict[str, float]


class BacktestEngine:
    """Each run has fresh accounting; supply a fresh stateful strategy per run.

    Orders last one session. Pending orders are cancelled before the next
    close's signals, including protective stops which must be reissued.
    Final inventory is marked to market, never forcibly liquidated.
    """
    def __init__(self, initial_cash: float = 100_000.0,
                 commission: CommissionModel | None = None,
                 slippage: SlippageModel | None = None, lot_size: int = 100,
                 t_plus_one: bool = True, periods_per_year: int = 252) -> None:
        Portfolio(initial_cash)
        if not isinstance(periods_per_year, int) or periods_per_year <= 0:
            raise ValueError('periods_per_year must be positive')
        self.initial_cash, self.periods_per_year = initial_cash, periods_per_year
        self.broker = Broker(commission or CommissionModel(), slippage or SlippageModel(), lot_size, t_plus_one)

    def run(self, bars: Sequence[Bar], strategy: Strategy) -> BacktestResult:
        """Validate chronology before trading and retain every order's outcome."""
        bars = tuple(bars)
        if any(b.date <= a.date or b.symbol != a.symbol for a, b in zip(bars, bars[1:])):
            raise ValueError('bars must have one symbol and strictly increasing dates')
        portfolio, orders, pending = Portfolio(self.initial_cash), [], []
        equity = [portfolio.cash]
        for index, bar in enumerate(bars):
            used_volume = 0
            for order in pending:
                if order.quantity + used_volume > bar.volume and bar.volume > 0:
                    order.status, order.reason = OrderStatus.REJECTED, 'insufficient remaining bar volume'
                else:
                    self.broker.execute(order, bar, portfolio)
                if order.status == OrderStatus.FILLED:
                    used_volume += order.quantity
                elif order.status == OrderStatus.PENDING:
                    order.status = OrderStatus.CANCELLED
                    order.reason = order.reason or 'session expired'
            equity.append(portfolio.equity({bar.symbol: bar.close}))
            pending = list(strategy.on_bar(bars[:index + 1], portfolio))
            for order in pending:
                if order.status != OrderStatus.PENDING or any(order is old for old in orders):
                    raise ValueError('strategy must return fresh pending orders')
                if order.symbol != bar.symbol:
                    raise ValueError('strategy order symbol differs from data')
                orders.append(order)
        for order in pending:
            order.status, order.reason = OrderStatus.CANCELLED, 'end of data'
        return BacktestResult(portfolio, orders, equity, portfolio.trades,
                              calculate_metrics(equity, [t.pnl for t in portfolio.trades], self.periods_per_year))
