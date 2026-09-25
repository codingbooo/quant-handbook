# Quantitative backtesting framework

A modular Python 3.10+ framework using only the standard library at runtime.
Run directly from this directory; no installation is needed.

```sh
python3 -m unittest discover -v
python3 -m backtest
```

## Components

- `models.py`: validated daily bars, orders, lifecycle statuses and realized trades.
- `portfolio.py`: cash, FIFO inventory, entry-fee allocation and T+1 availability.
- `execution.py`: commission/minimum fee, optional sell tax, adverse slippage,
  market and stop execution, lot and liquidity constraints.
- `engine.py`: chronological execution, order history and marked equity curve.
- `strategies.py`: volume-confirmed dual SMA, bounded dynamic grid and ATR stops.
- `metrics.py`: total return, CAGR, maximum drawdown, win rate, profit-loss ratio,
  Sharpe, Sortino and Calmar ratios.
- `market.py`: seeded synthetic bull, bear and mean-reverting oscillating markets.

## Execution contract

Each run handles one symbol with strictly increasing daily dates. A strategy
receives the completed history and current portfolio through `on_bar`, then
returns fresh orders for the next session. It must treat the portfolio as
read-only. Orders execute in returned order, subject to remaining bar volume.
Unfilled orders expire after that session; strategies reissue protective stops.
Orders generated on the final bar are cancelled. Use a fresh strategy instance
for each independent run.

Market orders fill at the next open plus adverse slippage, clipped to that bar's
low/high. A sell stop fills at the lesser of open and stop when the low reaches
its trigger; buy stops work symmetrically. This models gaps through a stop.
No volume means no execution. A bar locked at its explicit upper limit blocks
buys; a bar locked at its lower limit blocks sells. A stop cannot guarantee an
exit when trading is blocked.

Buys use configurable lots (default 100 shares); sells may liquidate odd lots.
T+1 is enabled by default: today's purchases cannot be sold today. Orders are
all-or-none, rejected when cash, settled shares or daily volume are insufficient.
No leverage or shorts are supported. Defaults are illustrative: commission
0.03% with a minimum of 5 currency units, slippage 0.05%, and zero sell tax.
Configure these for the scenario being modeled.

Equity includes starting cash followed by each session's closing valuation.
Open positions remain marked to market at the end. Each sell execution is one
realized trade for win/loss statistics; FIFO entry fees and exit commissions
are included in its P&L. This definition also applies to partial exits.

## Metrics

Returns and drawdown are fractions, not percentages. CAGR uses the number of
observed daily periods and 252 periods/year by default. Sharpe uses sample
standard deviation and arithmetic annual risk-free rate divided by periods/year.
Sortino uses the root mean squared negative excess return across **all** periods.
Calmar is CAGR / maximum drawdown. Profit-loss ratio is mean positive realized
P&L / absolute mean negative P&L, rather than gross profit / gross loss.

No trades yield zero trade statistics. Positive numerators with zero risk or
loss denominators yield infinity; zero/zero yields zero. Sharpe with fewer than
two returns is zero. An all-zero unfunded account yields zero metrics. Negative
or nonfinite equity is invalid; bankruptcy at zero has a CAGR of -100%.
See metric docstrings and tests for exact conventions.

## Scope of the market model

Generated data uses overnight gaps, intraday ranges, movement-sensitive noisy
volumes, cent-rounded prices, configurable daily limits and weekday dates.
Regime parameters are illustrative and seeded paths are reproducible. Weekdays
are not an exchange holiday calendar. Corporate actions, dividends, auction
queues, order-book depth and partial fills are outside this daily-bar model.
The engine does not infer daily limits for user-supplied bars: populate
`limit_up` and `limit_down` to enforce them.

## Custom strategies

Strategies implement a single method; the broker remains responsible for
execution eligibility and affordability.

```python
from backtest import BacktestEngine, Order, Side
from backtest.market import generate_market_data

class BuyAndHold:
    def on_bar(self, history, portfolio):
        if len(history) == 1:
            return [Order(history[-1].symbol, Side.BUY, 100)]
        return []

bars = generate_market_data(num_bars=252, regime="bull", seed=42)
result = BacktestEngine(initial_cash=100_000).run(bars, BuyAndHold())
print(result.metrics)
print(result.portfolio.cash, result.portfolio.quantity("SYNTH"))
```

`BacktestResult` exposes `portfolio`, `orders`, `equity_curve`, `trades` and
`metrics`. Inspect each order's `status`, `reason`, `fill_price`, `commission`
and `filled_at` to audit executions.

## Built-in strategy settings

```python
from backtest import DualSMAStrategy, DynamicGridStrategy, TrailingStopATRStrategy

sma = DualSMAStrategy(fast_period=5, slow_period=20, vol_period=20,
                      vol_multiplier=1.2, quantity=100)
grid = DynamicGridStrategy(floor_price=80, ceiling_price=120, grid_step=2,
                           trailing_stop_pct=0.05, quantity=100)
atr = TrailingStopATRStrategy(atr_period=14, atr_multiplier=2,
                             profit_lock_activation=0.05,
                             profit_lock_fraction=0.5, quantity=100)
```

SMA enters on an upward crossover confirmed against a volume average including
the current bar, and exits on a downward crossover. A blocked exit is retried
until the position closes. It needs enough bars for
both today's and yesterday's averages.

Grid buys a tranche per downward level crossing and sells a tranche per upward
crossing. Levels are anchored to the floor, or an optional `base_price`. Entry
must be strictly inside the floor/ceiling. Spacing must be representable and
produce at most 10,000 grid intervals. Its protective stop follows the
highest observed price while invested and is bounded below by the floor.

ATR uses a simple average of true ranges (including overnight gaps), then
ratchets a stop below the highest observed price. Once the activation gain is
reached, it also locks a configurable fraction of peak profit. Its optional
auto-entry supplies one initial position after warmup; the strategy then manages
that position without automatically reopening after exit. A blocked initial buy
is retried until a position is observed; a blocked exit remains scheduled until
the position is closed. Set `auto_enter=False`
when composing it with an external entry policy. Stops updated from today's
high become eligible next session, so no unknown intraday price ordering is
assumed. Strategy quantities and the broker's lot size should agree.
