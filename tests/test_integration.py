"""Reconcile complete strategy runs against their execution audit trails."""
import unittest
from backtest import (BacktestEngine, DualSMAStrategy, DynamicGridStrategy,
                      TrailingStopATRStrategy, Side, OrderStatus, generate_market_data)


class IntegrationTests(unittest.TestCase):
    def test_every_strategy_and_regime_reconciles(self):
        factories = [DualSMAStrategy,
                     lambda: DynamicGridStrategy(80, 120, 2),
                     TrailingStopATRStrategy]
        for regime in ('bull', 'bear', 'oscillating'):
            bars = generate_market_data(504, regime=regime, seed=42)
            for factory in factories:
                strategy = factory()
                with self.subTest(regime=regime, strategy=type(strategy).__name__):
                    result = BacktestEngine().run(bars, strategy)
                    cash, quantity = 100000.0, 0
                    filled = [o for o in result.orders if o.status == OrderStatus.FILLED]
                    self.assertGreater(len(filled), 0)
                    for order in filled:
                        direction = 1 if order.side == Side.BUY else -1
                        quantity += direction * order.quantity
                        cash -= direction * order.quantity * order.fill_price + order.commission
                        self.assertGreaterEqual(cash, -1e-8)
                        self.assertGreaterEqual(quantity, 0)
                    self.assertAlmostEqual(cash, result.portfolio.cash)
                    self.assertEqual(quantity, result.portfolio.quantity('SYNTH'))
                    self.assertAlmostEqual(result.equity_curve[-1], cash + quantity * bars[-1].close)
                    unrealized = sum(lot.quantity * (bars[-1].close - lot.price - lot.entry_fee_per_share)
                                     for lot in result.portfolio.positions.get('SYNTH', []))
                    self.assertAlmostEqual(result.equity_curve[-1] - 100000,
                                           sum(t.pnl for t in result.trades) + unrealized)
                    self.assertTrue(all(o.status != OrderStatus.PENDING for o in result.orders))


if __name__ == '__main__':
    unittest.main()
