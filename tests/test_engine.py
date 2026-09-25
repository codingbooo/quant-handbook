"""Execution and accounting regression tests."""
import unittest
from datetime import date, timedelta
from backtest.models import Bar, Order, Side, OrderType, OrderStatus
from backtest.portfolio import Portfolio
from backtest.execution import Broker, CommissionModel, SlippageModel
from backtest.engine import BacktestEngine


D = date(2024, 1, 2)


def bar(day=0, price=10, **kwargs):
    return Bar(D + timedelta(days=day), price, kwargs.pop('high', price),
               kwargs.pop('low', price), kwargs.pop('close', price),
               kwargs.pop('volume', 10000), **kwargs)


class Script:
    def __init__(self, signals):
        self.signals = signals
        self.lengths = []

    def on_bar(self, history, portfolio):
        self.lengths.append(len(history))
        return self.signals.get(len(history), [])


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.broker = Broker(CommissionModel(0, 0), SlippageModel(0))

    def engine(self, cash=10000):
        return BacktestEngine(cash, CommissionModel(0, 0), SlippageModel(0))

    def test_next_open_no_lookahead_and_final_mark(self):
        buy = Order('SYNTH', Side.BUY, 100)
        strategy = Script({1: [buy]})
        result = self.engine().run([bar(), bar(1, 12), bar(2, 13)], strategy)
        self.assertEqual(buy.fill_price, 12)
        self.assertEqual(result.portfolio.cash, 8800)
        self.assertEqual(result.equity_curve, [10000, 10000, 10000, 10100])
        self.assertEqual(strategy.lengths, [1, 2, 3])
        self.assertEqual(result.trades, [])

    def test_zero_cash_rejects_and_empty_run(self):
        buy = Order('SYNTH', Side.BUY, 100)
        result = self.engine(0).run([bar(), bar(1)], Script({1: [buy]}))
        self.assertEqual(buy.status, OrderStatus.REJECTED)
        self.assertEqual(result.portfolio.cash, 0)
        self.assertEqual(self.engine().run([], Script({})).equity_curve, [10000])

    def test_fifo_partial_sales_include_all_fees(self):
        p = Portfolio(10000)
        p.fill('SYNTH', Side.BUY, 100, 10, 5, D)
        p.fill('SYNTH', Side.BUY, 100, 12, 5, D)
        p.fill('SYNTH', Side.SELL, 150, 15, 5, D + timedelta(days=1))
        self.assertAlmostEqual(p.trades[0].pnl, 637.5)
        self.assertEqual(p.quantity('SYNTH'), 50)
        self.assertEqual(p.cash, 10035)
        p.fill('SYNTH', Side.SELL, 50, 11, 5, D + timedelta(days=2))
        self.assertAlmostEqual(sum(t.pnl for t in p.trades), p.cash - 10000)

    def test_t_plus_one_and_no_short(self):
        p = Portfolio(2000)
        p.fill('SYNTH', Side.BUY, 100, 10, 0, D)
        sell = Order('SYNTH', Side.SELL, 100)
        self.broker.execute(sell, bar(), p)
        self.assertEqual(sell.status, OrderStatus.REJECTED)
        self.assertEqual(p.quantity('SYNTH'), 100)
        with self.assertRaises(ValueError):
            p.fill('SYNTH', Side.SELL, 200, 10, 0, D, False)
        p.fill('SYNTH', Side.SELL, 100, 10, 0, D, False)
        self.assertEqual(p.cash, 2000)

    def test_gap_down_stop_fills_at_open(self):
        p = Portfolio(2000)
        p.fill('SYNTH', Side.BUY, 100, 10, 0, D)
        stop = Order('SYNTH', Side.SELL, 100, OrderType.STOP, 9)
        self.broker.execute(stop, bar(1, 8, high=8.5, low=7.8), p)
        self.assertEqual(stop.fill_price, 8)
        self.assertEqual(p.trades[0].pnl, -200)

    def test_intraday_stop_and_untriggered_stop(self):
        p = Portfolio(2000)
        p.fill('SYNTH', Side.BUY, 100, 10, 0, D)
        stop = Order('SYNTH', Side.SELL, 100, OrderType.STOP, 9)
        self.broker.execute(stop, bar(1, 10, low=9.5), p)
        self.assertEqual(stop.status, OrderStatus.PENDING)
        self.broker.execute(stop, bar(2, 10, low=8), p)
        self.assertEqual(stop.fill_price, 9)

    def test_limit_down_blocks_sell_limit_up_blocks_buy(self):
        p = Portfolio(2000)
        p.fill('SYNTH', Side.BUY, 100, 10, 0, D)
        sell = Order('SYNTH', Side.SELL, 100, OrderType.STOP, 9.5)
        self.broker.execute(sell, bar(1, 9, limit_down=9), p)
        self.assertEqual(sell.status, OrderStatus.PENDING)
        self.assertEqual(p.quantity('SYNTH'), 100)
        buy = Order('SYNTH', Side.BUY, 100)
        self.broker.execute(buy, bar(1, 11, limit_up=11), p)
        self.assertEqual(buy.reason, 'locked price limit')
        self.broker.execute(sell, bar(2, 9, high=9.2, limit_down=9), p)
        self.assertEqual(sell.status, OrderStatus.FILLED)

    def test_fees_and_adverse_slippage(self):
        broker = Broker(CommissionModel(0.001, 5, 0.001), SlippageModel(0.01))
        p = Portfolio(10000)
        buy = Order('SYNTH', Side.BUY, 100)
        broker.execute(buy, bar(high=11, low=9), p)
        self.assertEqual(buy.fill_price, 10.1)
        self.assertEqual(p.cash, 8985)
        sell = Order('SYNTH', Side.SELL, 100)
        broker.execute(sell, bar(1, high=11, low=9), p)
        self.assertEqual(sell.fill_price, 9.9)
        self.assertAlmostEqual(sell.commission, 5.99)
        self.assertAlmostEqual(p.trades[0].pnl, -30.99)

    def test_volume_lots_and_end_cancellation(self):
        p = Portfolio(10000)
        odd = Order('SYNTH', Side.BUY, 1)
        self.broker.execute(odd, bar(), p)
        self.assertEqual(odd.status, OrderStatus.REJECTED)
        frozen = Order('SYNTH', Side.BUY, 100)
        self.broker.execute(frozen, bar(volume=0), p)
        self.assertEqual(frozen.status, OrderStatus.PENDING)
        orders = [Order('SYNTH', Side.BUY, 100) for _ in range(2)]
        last = Order('SYNTH', Side.BUY, 100)
        self.engine().run([bar(), bar(1, volume=100)], Script({1: orders, 2: [last]}))
        self.assertEqual([o.status for o in orders], [OrderStatus.FILLED, OrderStatus.REJECTED])
        self.assertEqual(last.reason, 'end of data')

    def test_stop_buy_gap_and_slippage_clipping(self):
        p = Portfolio(10000)
        buy = Order('SYNTH', Side.BUY, 100, OrderType.STOP, 11)
        self.broker.execute(buy, bar(1, 12, high=13, low=11), p)
        self.assertEqual(buy.fill_price, 12)
        clipped = Order('SYNTH', Side.BUY, 100)
        Broker(CommissionModel(0, 0), SlippageModel(0.2)).execute(clipped, bar(2), p)
        self.assertEqual(clipped.fill_price, 10)

    def test_rejected_fees_leave_account_unchanged(self):
        p = Portfolio(1000)
        buy = Order('SYNTH', Side.BUY, 100)
        Broker(CommissionModel(0, 5), SlippageModel(0)).execute(buy, bar(), p)
        self.assertEqual(buy.status, OrderStatus.REJECTED)
        self.assertEqual(p.cash, 1000)
        self.assertEqual(p.quantity('SYNTH'), 0)

    def test_order_expiry_and_repeated_run_isolation(self):
        engine = self.engine()
        buy = Order('SYNTH', Side.BUY, 100, OrderType.STOP, 20)
        result = engine.run([bar(), bar(1), bar(2, 21)], Script({1: [buy]}))
        self.assertEqual(buy.status, OrderStatus.CANCELLED)
        self.assertEqual(buy.reason, 'session expired')
        self.assertEqual(result.portfolio.quantity('SYNTH'), 0)
        result = engine.run([bar(), bar(1)], Script({1: [Order('SYNTH', Side.BUY, 100)]}))
        self.assertEqual(result.portfolio.quantity('SYNTH'), 100)
        self.assertEqual(engine.run([bar()], Script({})).portfolio.quantity('SYNTH'), 0)

    def test_invalid_inputs(self):
        for cash in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                Portfolio(cash)
        with self.assertRaises(ValueError):
            self.engine().run([bar(1), bar()], Script({}))
        with self.assertRaises(ValueError):
            Bar(D, 10, 9, 8, 10, 100)
        with self.assertRaises(ValueError):
            Order('SYNTH', Side.BUY, 0)
        with self.assertRaises(ValueError):
            Order('SYNTH', Side.SELL, 100, OrderType.STOP)
        for factory in (lambda: CommissionModel(-1), lambda: SlippageModel(1),
                        lambda: BacktestEngine(lot_size=0)):
            with self.assertRaises(ValueError):
                factory()


if __name__ == '__main__':
    unittest.main()
