"""Unit and integration tests for trading strategies and backtest engine interaction."""
from datetime import date, timedelta
import unittest

from backtest.engine import BacktestEngine
from backtest.execution import CommissionModel, SlippageModel
from backtest.models import Bar, Order, OrderStatus, OrderType, Side
from backtest.portfolio import Portfolio
from backtest.strategies import DualSMAStrategy, DynamicGridStrategy, TrailingStopATRStrategy


def make_bar(
    day_offset: int,
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    volume: int = 10000,
    symbol: str = "TEST",
    limit_up: float | None = None,
    limit_down: float | None = None,
) -> Bar:
    """Helper to create valid bars with sequential dates."""
    return Bar(
        date=date(2025, 1, 1) + timedelta(days=day_offset),
        open=float(open_p),
        high=float(high_p),
        low=float(low_p),
        close=float(close_p),
        volume=volume,
        symbol=symbol,
        limit_up=limit_up,
        limit_down=limit_down,
    )


class TestDualSMAStrategy(unittest.TestCase):
    def test_parameter_validations(self):
        with self.assertRaises(ValueError):
            DualSMAStrategy(fast_period=0)
        with self.assertRaises(ValueError):
            DualSMAStrategy(fast_period=20, slow_period=5)  # fast >= slow
        with self.assertRaises(ValueError):
            DualSMAStrategy(fast_period=10, slow_period=10)  # fast == slow
        with self.assertRaises(ValueError):
            DualSMAStrategy(vol_period=0)
        with self.assertRaises(ValueError):
            DualSMAStrategy(vol_multiplier=-0.1)
        with self.assertRaises(ValueError):
            DualSMAStrategy(lot_size=0)
        with self.assertRaises(ValueError):
            DualSMAStrategy(quantity=150, lot_size=100)  # not multiple of lot_size

    def test_warmup_and_volume_confirmation(self):
        strat = DualSMAStrategy(fast_period=2, slow_period=4, vol_period=4, vol_multiplier=1.5, quantity=100)
        portfolio = Portfolio(100000.0)

        # Need max(4, 4) + 1 = 5 bars
        bars = [
            make_bar(1, 10, 10, 10, 10, 1000),
            make_bar(2, 10, 10, 10, 10, 1000),
            make_bar(3, 10, 10, 10, 10, 1000),
            make_bar(4, 10, 10, 10, 10, 1000),
        ]
        self.assertEqual(strat.on_bar(bars, portfolio), [])

        # Bar 5: Bullish crossover, but volume is normal (1000, average 1000 < 1.5 * average)
        bars.append(make_bar(5, 12, 12, 12, 12, 1000))
        orders = strat.on_bar(bars, portfolio)
        self.assertEqual(orders, [])  # volume unconfirmed

        # Replace bar 5 with high volume confirmation (2500 >= 1000 * 1.5)
        bars[-1] = make_bar(5, 12, 12, 12, 12, 2500)
        orders = strat.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, Side.BUY)
        self.assertEqual(orders[0].quantity, 100)
        self.assertEqual(orders[0].order_type, OrderType.MARKET)

    def test_death_cross_and_no_shorts(self):
        strat = DualSMAStrategy(fast_period=2, slow_period=3, vol_period=3, vol_multiplier=1.0, quantity=100)
        portfolio = Portfolio(100000.0)

        # Downtrend causing death cross
        bars = [
            make_bar(1, 20, 20, 20, 20, 1000),
            make_bar(2, 20, 20, 20, 20, 1000),
            make_bar(3, 20, 20, 20, 20, 1000),
            make_bar(4, 15, 15, 15, 15, 1000),
        ]
        # Flat: no accidental short
        self.assertEqual(strat.on_bar(bars, portfolio), [])

        # In position: generates market sell for all held shares
        portfolio.fill("TEST", Side.BUY, 200, 20.0, 0.0, date(2025, 1, 4), t_plus_one=False)
        orders = strat.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, Side.SELL)
        self.assertEqual(orders[0].quantity, 200)
        self.assertEqual(orders[0].order_type, OrderType.MARKET)

    def test_locked_down_multi_day_retry(self):
        """Bearish death cross sell order blocked by locked limit-down is retried until filled."""
        strat = DualSMAStrategy(fast_period=2, slow_period=3, vol_period=3, vol_multiplier=1.0, quantity=100)
        engine = BacktestEngine(lot_size=100, t_plus_one=False)

        # Bar 1-3: flat at 20
        # Bar 4: rally to 25 -> golden cross -> buys on bar 5
        # Bar 5: price at 26 -> holds 100
        # Bar 6: price plunges to 15 -> death cross -> emits sell for bar 7
        # Bar 7: locked limit down at 12 (high <= limit_down) -> sell rejected!
        # Bar 8: normal bar at 10 -> sell retried and executed!
        bars = [
            make_bar(1, 20, 20, 20, 20, 5000),
            make_bar(2, 20, 20, 20, 20, 5000),
            make_bar(3, 20, 20, 20, 20, 5000),
            make_bar(4, 25, 25, 25, 25, 10000),
            make_bar(5, 26, 26, 26, 26, 5000),
            make_bar(6, 15, 15, 15, 15, 5000),
            make_bar(7, 12, 12, 12, 12, 5000, limit_down=12.0),
            make_bar(8, 10, 10, 10, 10, 5000),
        ]
        result = engine.run(bars, strat)
        self.assertEqual(result.portfolio.quantity("TEST"), 0)
        sell_orders = [o for o in result.orders if o.side == Side.SELL]
        self.assertGreaterEqual(len(sell_orders), 2)

    def test_engine_execution_and_zero_cash(self):
        strat = DualSMAStrategy(fast_period=2, slow_period=3, vol_period=3, vol_multiplier=1.0, quantity=100)
        engine = BacktestEngine(
            initial_cash=100000.0,
            commission=CommissionModel(rate=0.0, minimum=0.0),
            slippage=SlippageModel(rate=0.0),
            lot_size=100,
            t_plus_one=True,
        )

        # Sequence: flat -> rally (golden cross) -> hold -> drop (death cross) -> final execution bar
        prices = [10.0, 10.0, 10.0, 12.0, 14.0, 11.0, 9.0, 8.5]
        bars = [make_bar(i, p, p + 0.5, p - 0.5, p, 5000) for i, p in enumerate(prices, 1)]

        result = engine.run(bars, strat)
        self.assertTrue(len(result.trades) > 0)
        self.assertEqual(result.portfolio.quantity("TEST"), 0)
        self.assertTrue("total_return" in result.metrics)

        # Zero cash engine run
        zero_engine = BacktestEngine(
            initial_cash=0.0,
            commission=CommissionModel(rate=0.0, minimum=0.0),
            slippage=SlippageModel(rate=0.0),
            lot_size=100,
            t_plus_one=True,
        )
        strat_zero = DualSMAStrategy(fast_period=2, slow_period=3, vol_period=3, vol_multiplier=1.0, quantity=100)
        zero_result = zero_engine.run(bars, strat_zero)
        self.assertEqual(zero_result.portfolio.quantity("TEST"), 0)
        self.assertEqual(zero_result.portfolio.cash, 0.0)
        rejected_orders = [o for o in zero_result.orders if o.status == OrderStatus.REJECTED]
        self.assertTrue(len(rejected_orders) > 0)
        self.assertEqual(rejected_orders[0].reason, "insufficient cash")


class TestDynamicGridStrategy(unittest.TestCase):
    def test_parameter_validations(self):
        with self.assertRaises(ValueError):
            DynamicGridStrategy(floor_price=100, ceiling_price=90, grid_step=5)
        with self.assertRaises(ValueError):
            DynamicGridStrategy(floor_price=90, ceiling_price=100, grid_step=0)
        with self.assertRaises(ValueError):
            DynamicGridStrategy(floor_price=90, ceiling_price=100, grid_step=1e-20)  # unrepresentable step
        with self.assertRaises(ValueError):
            DynamicGridStrategy(floor_price=0.01, ceiling_price=1000.0, grid_step=0.001)  # > 10000 levels
        with self.assertRaises(ValueError):
            DynamicGridStrategy(floor_price=90, ceiling_price=100, grid_step=5, trailing_stop_pct=1.5)
        with self.assertRaises(ValueError):
            DynamicGridStrategy(floor_price=90, ceiling_price=100, grid_step=5, base_price=120)  # above ceiling
        with self.assertRaises(ValueError):
            DynamicGridStrategy(floor_price=90, ceiling_price=100, grid_step=5, quantity=150, lot_size=100)

    def test_grid_level_generation(self):
        grid = DynamicGridStrategy(floor_price=80.0, ceiling_price=120.0, grid_step=2.0, base_price=100.0)
        self.assertEqual(grid.levels[0], 82.0)
        self.assertEqual(grid.levels[-1], 118.0)
        self.assertIn(100.0, grid.levels)
        self.assertEqual(len(grid.levels), 19)

    def test_cross_buys_and_sells_without_accidental_shorts(self):
        grid = DynamicGridStrategy(floor_price=80.0, ceiling_price=120.0, grid_step=5.0, base_price=100.0, quantity=100)
        portfolio = Portfolio(100000.0)

        # Bar 1: at 102.0
        bars = [make_bar(1, 102, 103, 101, 102)]
        self.assertEqual(grid.on_bar(bars, portfolio), [])

        # Bar 2: drops through 100.0 and 95.0 down to 93.0
        bars.append(make_bar(2, 102, 102, 92, 93))
        orders = grid.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, Side.BUY)
        self.assertEqual(orders[0].quantity, 200)  # crossed 2 levels downwards

        # Bar 3: rises through 95.0 and 100.0 to 101.0, but portfolio holds 0
        bars.append(make_bar(3, 93, 102, 93, 101))
        orders = grid.on_bar(bars, portfolio)
        self.assertEqual(orders, [])  # flat -> no short order

        # Now suppose portfolio holds 100 shares
        portfolio.fill("TEST", Side.BUY, 100, 93.0, 0.0, date(2025, 1, 3), t_plus_one=False)
        orders = grid.on_bar(bars, portfolio)
        market_sells = [o for o in orders if o.order_type == OrderType.MARKET and o.side == Side.SELL]
        self.assertEqual(len(market_sells), 1)
        self.assertEqual(market_sells[0].quantity, 100)

    def test_ceiling_no_new_buys_and_hard_floor_exit(self):
        grid = DynamicGridStrategy(floor_price=90.0, ceiling_price=110.0, grid_step=5.0, base_price=100.0, quantity=100)
        portfolio = Portfolio(100000.0)

        # Close above ceiling: no new buys even on downward drop above ceiling
        bars = [
            make_bar(1, 115, 116, 114, 115),
            make_bar(2, 115, 115, 111, 112),
        ]
        self.assertEqual(grid.on_bar(bars, portfolio), [])

        # Hard floor exit: close drops to or below floor_price (90.0)
        portfolio.fill("TEST", Side.BUY, 100, 95.0, 0.0, date(2025, 1, 2), t_plus_one=False)
        bars.append(make_bar(3, 92, 92, 88, 89))  # close = 89 <= 90
        orders = grid.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, Side.SELL)
        self.assertEqual(orders[0].quantity, 100)
        self.assertEqual(orders[0].order_type, OrderType.MARKET)

    def test_trailing_stop_exit(self):
        grid = DynamicGridStrategy(floor_price=80.0, ceiling_price=150.0, grid_step=5.0, trailing_stop_pct=0.10, quantity=100)
        portfolio = Portfolio(100000.0)
        portfolio.fill("TEST", Side.BUY, 100, 100.0, 0.0, date(2025, 1, 1), t_plus_one=False)

        # High reaches 120.0, close 118.0 -> trailing stop is 120 * 0.9 = 108.0
        bars = [make_bar(1, 100, 120, 100, 118)]
        orders = grid.on_bar(bars, portfolio)
        stops = [o for o in orders if o.order_type == OrderType.STOP]
        self.assertEqual(len(stops), 1)
        self.assertAlmostEqual(stops[0].stop_price, 108.0)

        # Next bar close drops to 105.0 <= 108.0 -> trailing exit triggers MARKET SELL
        bars.append(make_bar(2, 118, 118, 104, 105))
        orders = grid.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, Side.SELL)
        self.assertEqual(orders[0].order_type, OrderType.MARKET)
        self.assertEqual(orders[0].quantity, 100)

    def test_locked_down_multi_day_retry(self):
        """When sell is blocked by locked limit-down, strategy retries until executed."""
        grid = DynamicGridStrategy(floor_price=90.0, ceiling_price=110.0, grid_step=2.0, base_price=100.0, quantity=100)
        engine = BacktestEngine(lot_size=100, t_plus_one=False)

        # Bar 1: close 101
        # Bar 2: drops to 97 -> buys 200 shares (crossing 100 and 98)
        # Bar 3: fills 200 shares. Close drops to 85 (below floor 90) -> emits sell for bar 4
        # Bar 4: locked limit down at 80 (high <= limit_down) -> sell rejected!
        # Bar 5: locked limit down at 75 -> sell rejected!
        # Bar 6: normal bar at 70 -> sell finally fills!
        bars = [
            make_bar(1, 101, 102, 100, 101, 10000),
            make_bar(2, 101, 101, 96, 97, 10000),
            make_bar(3, 97, 97, 85, 85, 10000),
            make_bar(4, 80, 80, 80, 80, 10000, limit_down=80.0),
            make_bar(5, 75, 75, 75, 75, 10000, limit_down=75.0),
            make_bar(6, 70, 72, 68, 70, 10000),
        ]
        result = engine.run(bars, grid)
        # Position should eventually be liquidated
        self.assertEqual(result.portfolio.quantity("TEST"), 0)
        # Verify blocked sell orders were re-emitted
        sell_orders = [o for o in result.orders if o.side == Side.SELL and o.order_type == OrderType.MARKET]
        self.assertGreaterEqual(len(sell_orders), 3)

    def test_engine_execution_and_zero_cash(self):
        grid = DynamicGridStrategy(floor_price=80.0, ceiling_price=120.0, grid_step=5.0, base_price=100.0, quantity=100)
        engine = BacktestEngine(
            initial_cash=100000.0,
            commission=CommissionModel(rate=0.0, minimum=0.0),
            slippage=SlippageModel(rate=0.0),
            lot_size=100,
            t_plus_one=True,
        )
        # Oscillating prices around grid levels, then drop through floor
        prices = [102.0, 94.0, 94.0, 101.0, 101.0, 85.0, 78.0, 75.0]
        bars = [make_bar(i, p, p + 1.0, p - 1.0, p, 10000) for i, p in enumerate(prices, 1)]

        result = engine.run(bars, grid)
        self.assertTrue(len(result.orders) > 0)
        self.assertEqual(result.portfolio.quantity("TEST"), 0)  # exited on floor breach

        # Zero cash engine run
        zero_engine = BacktestEngine(
            initial_cash=0.0,
            commission=CommissionModel(rate=0.0, minimum=0.0),
            slippage=SlippageModel(rate=0.0),
            lot_size=100,
            t_plus_one=True,
        )
        strat_zero = DynamicGridStrategy(floor_price=80.0, ceiling_price=120.0, grid_step=5.0, quantity=100)
        zero_result = zero_engine.run(bars, strat_zero)
        self.assertEqual(zero_result.portfolio.quantity("TEST"), 0)
        rejected_orders = [o for o in zero_result.orders if o.status == OrderStatus.REJECTED]
        self.assertTrue(len(rejected_orders) > 0)


class TestTrailingStopATRStrategy(unittest.TestCase):
    def test_parameter_validations(self):
        with self.assertRaises(ValueError):
            TrailingStopATRStrategy(atr_period=0)
        with self.assertRaises(ValueError):
            TrailingStopATRStrategy(atr_multiplier=0.0)
        with self.assertRaises(ValueError):
            TrailingStopATRStrategy(profit_lock_activation=-0.1)
        with self.assertRaises(ValueError):
            TrailingStopATRStrategy(profit_lock_fraction=1.2)
        with self.assertRaises(ValueError):
            TrailingStopATRStrategy(auto_enter="yes")  # type: ignore

    def test_warmup_and_auto_enter_retry_until_filled(self):
        strat = TrailingStopATRStrategy(atr_period=3, auto_enter=True, quantity=100)
        portfolio = Portfolio(100000.0)

        bars = [
            make_bar(1, 10, 10.2, 9.8, 10),
            make_bar(2, 10, 10.2, 9.8, 10),
            make_bar(3, 10, 10.2, 9.8, 10),
        ]
        # atr_period = 3 needs 4 bars
        self.assertEqual(strat.on_bar(bars, portfolio), [])

        bars.append(make_bar(4, 10, 10.2, 9.8, 10))
        orders = strat.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, Side.BUY)
        self.assertEqual(orders[0].quantity, 100)

        # If order was cancelled / not filled, next bar continues retrying buy
        bars.append(make_bar(5, 10, 10.2, 9.8, 10))
        orders = strat.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, Side.BUY)

        # Once position is filled, auto-enter stops emitting buys and starts issuing stops
        portfolio.fill("TEST", Side.BUY, 100, 10.0, 0.0, date(2025, 1, 5), t_plus_one=False)
        bars.append(make_bar(6, 10, 10.2, 9.8, 10))
        orders = strat.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, Side.SELL)  # protective stop order, not buy!
        self.assertEqual(orders[0].order_type, OrderType.STOP)

    def test_stop_never_loosens_and_profit_lock(self):
        strat = TrailingStopATRStrategy(
            atr_period=2,
            atr_multiplier=1.0,
            profit_lock_activation=0.10,
            profit_lock_fraction=0.50,
            quantity=100,
            auto_enter=False,
        )
        portfolio = Portfolio(100000.0)
        portfolio.fill("TEST", Side.BUY, 100, 100.0, 0.0, date(2025, 1, 3), t_plus_one=False)

        # Entry at 100. ATR ~ 2.0. High = 101. Initial stop = 101 - 1*2 = 99.
        bars = [
            make_bar(1, 100, 101, 99, 100),
            make_bar(2, 100, 101, 99, 100),
            make_bar(3, 100, 101, 99, 100),
        ]
        orders = strat.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertAlmostEqual(orders[0].stop_price, 99.0)

        # Rally to high 120 (+20% gain, triggers profit lock >= 10%)
        # Accrued profit = 20.0 -> locks 50% = 10.0 -> locked stop = 110.0
        # ATR is (120 - 99) = 21, ATR candidate is 120 - 21 = 99 -> locked stop (110) dominates!
        bars.append(make_bar(4, 105, 120, 104, 118))
        orders = strat.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertAlmostEqual(orders[0].stop_price, 110.0)

        # Pullback: high 115, close 112 -> stop MUST NOT LOOSEN (remains >= 110.0)
        bars.append(make_bar(5, 115, 115, 111, 112))
        orders = strat.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertGreaterEqual(orders[0].stop_price, 110.0)

        # Plunge below stop: close 108 <= 110 -> triggers MARKET SELL
        bars.append(make_bar(6, 111, 111, 107, 108))
        orders = strat.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, Side.SELL)
        self.assertEqual(orders[0].order_type, OrderType.MARKET)

    def test_immediate_profit_lock_activation_zero(self):
        # activation=0.0 activates immediately on any positive profit
        strat = TrailingStopATRStrategy(
            atr_period=2,
            atr_multiplier=5.0,  # wide ATR stop
            profit_lock_activation=0.0,
            profit_lock_fraction=0.8,
            quantity=100,
            auto_enter=False,
        )
        portfolio = Portfolio(100000.0)
        portfolio.fill("TEST", Side.BUY, 100, 100.0, 0.0, date(2025, 1, 3), t_plus_one=False)

        # High reaches 105.0 (+5.0 profit). Locked stop = 100 + 5.0 * 0.8 = 104.0.
        # Close is 104.5 > 104.0 -> reissues STOP order with stop_price = 104.0!
        bars = [
            make_bar(1, 100, 100.5, 99.5, 100),
            make_bar(2, 100, 100.5, 99.5, 100),
            make_bar(3, 100, 105.0, 100.0, 104.5),
        ]
        orders = strat.on_bar(bars, portfolio)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].order_type, OrderType.STOP)
        self.assertAlmostEqual(orders[0].stop_price, 104.0)

    def test_engine_execution_and_zero_cash(self):
        strat = TrailingStopATRStrategy(atr_period=2, atr_multiplier=1.5, quantity=100, auto_enter=True)
        engine = BacktestEngine(
            initial_cash=100000.0,
            commission=CommissionModel(rate=0.0, minimum=0.0),
            slippage=SlippageModel(rate=0.0),
            lot_size=100,
            t_plus_one=True,
        )
        # Warmup (bars 1-3), buy on bar 4 open, rally, sharp gap down triggering stop
        prices = [50.0, 50.0, 50.0, 55.0, 60.0, 65.0, 55.0, 50.0]
        bars = [make_bar(i, p, p + 1.0, p - 1.0, p, 10000) for i, p in enumerate(prices, 1)]

        result = engine.run(bars, strat)
        self.assertTrue(len(result.trades) > 0)
        self.assertEqual(result.portfolio.quantity("TEST"), 0)

        # Zero cash engine run
        zero_engine = BacktestEngine(
            initial_cash=0.0,
            commission=CommissionModel(rate=0.0, minimum=0.0),
            slippage=SlippageModel(rate=0.0),
            lot_size=100,
            t_plus_one=True,
        )
        strat_zero = TrailingStopATRStrategy(atr_period=2, quantity=100, auto_enter=True)
        zero_result = zero_engine.run(bars, strat_zero)
        self.assertEqual(zero_result.portfolio.quantity("TEST"), 0)
        rejected_orders = [o for o in zero_result.orders if o.status == OrderStatus.REJECTED]
        self.assertTrue(len(rejected_orders) > 0)


if __name__ == "__main__":
    unittest.main()
