"""Unit tests for backtest.metrics."""

import math
import unittest

from backtest.metrics import calculate_metrics


class TestMetrics(unittest.TestCase):
    def test_known_values_basic(self):
        # 3 equity points => 2 periods (n - 1 returns)
        # Returns: (105 - 100)/100 = 0.05, (110.25 - 105)/105 = 0.05
        # Total return = (110.25 - 100) / 100 = 0.1025
        # With periods_per_year = 2, years = 2/2 = 1.0 => CAGR = 0.1025
        equity = [100.0, 105.0, 110.25]
        metrics = calculate_metrics(
            equity=equity,
            trade_pnls=[5.0, 5.25],
            periods_per_year=2,
            risk_free_rate=0.0,
        )

        self.assertAlmostEqual(metrics["total_return"], 0.1025, places=6)
        self.assertAlmostEqual(metrics["cagr"], 0.1025, places=6)
        self.assertEqual(metrics["max_drawdown"], 0.0)
        # Stdev of returns [0.05, 0.05] is 0.0, mean excess > 0 => inf
        self.assertEqual(metrics["sharpe_ratio"], float("inf"))
        # Downside returns are all 0 => downside stdev 0.0 => inf
        self.assertEqual(metrics["sortino_ratio"], float("inf"))
        # Drawdown is 0.0, cagr > 0 => inf
        self.assertEqual(metrics["calmar_ratio"], float("inf"))
        self.assertEqual(metrics["win_rate"], 1.0)
        self.assertEqual(metrics["profit_loss_ratio"], float("inf"))

    def test_known_drawdown_calculation(self):
        # Peak reaches 120.0, trough hits 80.0 => max_drawdown = (120 - 80) / 120 = 40/120 = 1/3
        equity = [100.0, 120.0, 90.0, 110.0, 80.0, 100.0]
        metrics = calculate_metrics(equity=equity)

        expected_mdd = 40.0 / 120.0
        self.assertAlmostEqual(metrics["max_drawdown"], expected_mdd, places=7)
        self.assertAlmostEqual(metrics["total_return"], 0.0, places=7)
        self.assertAlmostEqual(metrics["cagr"], 0.0, places=7)
        self.assertAlmostEqual(metrics["calmar_ratio"], 0.0, places=7)

    def test_exact_analytical_sharpe_and_sortino(self):
        # Equity: [100.0, 104.0, 101.92]
        # Returns:
        #   r_1 = (104 - 100) / 100 = 0.04
        #   r_2 = (101.92 - 104) / 104 = -0.02
        # Number of periods M = 2.
        # Mean return = (0.04 + (-0.02)) / 2 = 0.01
        # With risk_free_rate = 0.0, excess returns = [0.04, -0.02], mean excess = 0.01
        # Sample variance (ddof=1) = ((0.04 - 0.01)^2 + (-0.02 - 0.01)^2) / 1 = 0.0018
        # Sample stdev = sqrt(0.0018)
        # Expected Sharpe = (0.01 / sqrt(0.0018)) * sqrt(252) = sqrt(14) ~= 3.7416573867739413
        #
        # Downside deviations: min(excess, 0) = [0.0, -0.02]
        # Downside squared sum = 0.0^2 + (-0.02)^2 = 0.0004
        # Downside mean sq = 0.0004 / 2 = 0.0002
        # Downside stdev = sqrt(0.0002)
        # Expected Sortino = (0.01 / sqrt(0.0002)) * sqrt(252) = 3 * sqrt(14) ~= 11.224972160321824
        equity = [100.0, 104.0, 101.92]
        metrics = calculate_metrics(
            equity=equity,
            periods_per_year=252,
            risk_free_rate=0.0,
        )

        expected_sharpe = math.sqrt(14.0)
        expected_sortino = 3.0 * math.sqrt(14.0)

        self.assertAlmostEqual(metrics["sharpe_ratio"], expected_sharpe, places=9)
        self.assertAlmostEqual(metrics["sortino_ratio"], expected_sortino, places=9)

    def test_sharpe_with_risk_free_rate(self):
        # Returns: [0.04, -0.02], periods_per_year = 2, rf = 0.02
        # rf_period = 0.02 / 2 = 0.01
        # Excess returns: [0.03, -0.03], mean excess = 0.0
        equity = [100.0, 104.0, 101.92]
        metrics = calculate_metrics(
            equity=equity,
            periods_per_year=2,
            risk_free_rate=0.02,
        )
        self.assertAlmostEqual(metrics["sharpe_ratio"], 0.0, places=9)
        self.assertAlmostEqual(metrics["sortino_ratio"], 0.0, places=9)

    def test_trade_pnl_statistics(self):
        # 4 trades: 2 positive, 2 negative
        trade_pnls = [100.0, -50.0, 200.0, -150.0]
        # Win rate: 2 / 4 = 0.5
        # Winners: [100, 200], mean = 150
        # Losers: [-50, -150], mean = -100, abs = 100
        # Profit/loss ratio: 150 / 100 = 1.5
        metrics = calculate_metrics(equity=[100.0, 105.0], trade_pnls=trade_pnls)

        self.assertEqual(metrics["win_rate"], 0.5)
        self.assertAlmostEqual(metrics["profit_loss_ratio"], 1.5, places=7)

    def test_trade_pnl_edge_cases(self):
        # 1. Empty trade_pnls
        m_empty = calculate_metrics(equity=[100.0, 105.0], trade_pnls=[])
        self.assertEqual(m_empty["win_rate"], 0.0)
        self.assertEqual(m_empty["profit_loss_ratio"], 0.0)

        # 2. All winning trades
        m_wins = calculate_metrics(equity=[100.0, 105.0], trade_pnls=[10.0, 20.0])
        self.assertEqual(m_wins["win_rate"], 1.0)
        self.assertEqual(m_wins["profit_loss_ratio"], float("inf"))

        # 3. All losing trades
        m_losses = calculate_metrics(equity=[100.0, 105.0], trade_pnls=[-10.0, -20.0])
        self.assertEqual(m_losses["win_rate"], 0.0)
        self.assertEqual(m_losses["profit_loss_ratio"], 0.0)

        # 4. All zero trades
        m_zeros = calculate_metrics(equity=[100.0, 105.0], trade_pnls=[0.0, 0.0])
        self.assertEqual(m_zeros["win_rate"], 0.0)
        self.assertEqual(m_zeros["profit_loss_ratio"], 0.0)

        # 5. Mixed with zero trades
        m_mixed = calculate_metrics(equity=[100.0, 105.0], trade_pnls=[100.0, 0.0, -50.0])
        self.assertAlmostEqual(m_mixed["win_rate"], 1.0 / 3.0, places=7)
        self.assertAlmostEqual(m_mixed["profit_loss_ratio"], 2.0, places=7)

    def test_single_value_equity_sequence(self):
        # Only 1 point => 0 return periods
        equity = [100.0]
        metrics = calculate_metrics(equity=equity)
        self.assertEqual(metrics["total_return"], 0.0)
        self.assertEqual(metrics["cagr"], 0.0)
        self.assertEqual(metrics["max_drawdown"], 0.0)
        self.assertEqual(metrics["sharpe_ratio"], 0.0)
        self.assertEqual(metrics["sortino_ratio"], 0.0)
        self.assertEqual(metrics["calmar_ratio"], 0.0)

    def test_flat_equity_curve(self):
        equity = [100.0, 100.0, 100.0, 100.0]
        metrics = calculate_metrics(equity=equity)
        self.assertEqual(metrics["total_return"], 0.0)
        self.assertEqual(metrics["cagr"], 0.0)
        self.assertEqual(metrics["max_drawdown"], 0.0)
        self.assertEqual(metrics["sharpe_ratio"], 0.0)
        self.assertEqual(metrics["sortino_ratio"], 0.0)
        self.assertEqual(metrics["calmar_ratio"], 0.0)

    def test_strictly_losing_equity_curve(self):
        # Constant negative returns: [100.0, 90.0, 81.0] -> returns [-0.10, -0.10]
        # Stdev = 0.0, mean excess < 0 => Sharpe = -inf
        equity = [100.0, 90.0, 81.0]
        metrics = calculate_metrics(equity=equity, periods_per_year=2)
        self.assertAlmostEqual(metrics["total_return"], -0.19, places=6)
        self.assertEqual(metrics["sharpe_ratio"], float("-inf"))
        self.assertAlmostEqual(metrics["max_drawdown"], 0.19, places=6)
        self.assertTrue(metrics["calmar_ratio"] < 0)

    def test_bankruptcy_zero_equity(self):
        # Equity hits exactly 0.0 after starting positive
        equity = [100.0, 50.0, 0.0, 0.0]
        metrics = calculate_metrics(equity=equity)
        self.assertEqual(metrics["total_return"], -1.0)
        self.assertEqual(metrics["cagr"], -1.0)
        self.assertEqual(metrics["max_drawdown"], 1.0)
        self.assertEqual(metrics["calmar_ratio"], -1.0)

    def test_all_zero_equity_returns_zeros(self):
        # All-zero equity curve returns 0.0 for all performance metrics
        equity = [0.0, 0.0, 0.0]
        metrics = calculate_metrics(equity=equity, trade_pnls=[])
        self.assertEqual(metrics["total_return"], 0.0)
        self.assertEqual(metrics["cagr"], 0.0)
        self.assertEqual(metrics["max_drawdown"], 0.0)
        self.assertEqual(metrics["sharpe_ratio"], 0.0)
        self.assertEqual(metrics["sortino_ratio"], 0.0)
        self.assertEqual(metrics["calmar_ratio"], 0.0)
        self.assertEqual(metrics["win_rate"], 0.0)
        self.assertEqual(metrics["profit_loss_ratio"], 0.0)

    def test_reject_zero_initial_then_positive_equity(self):
        # Zero starting capital cannot turn positive in long-only
        with self.assertRaises(ValueError):
            calculate_metrics(equity=[0.0, 10.0])

        with self.assertRaises(ValueError):
            calculate_metrics(equity=[0.0, 0.0, 50.0])

    def test_reject_negative_equity(self):
        # Any negative equity in long-only must be rejected
        with self.assertRaises(ValueError):
            calculate_metrics(equity=[-10.0, 10.0])

        with self.assertRaises(ValueError):
            calculate_metrics(equity=[100.0, -5.0])

        with self.assertRaises(ValueError):
            calculate_metrics(equity=[100.0, 50.0, -20.0])

    def test_input_validation_empty_and_types(self):
        with self.assertRaises(ValueError):
            calculate_metrics(equity=[])

        with self.assertRaises(ValueError):
            calculate_metrics(equity=100.0)  # type: ignore

        with self.assertRaises(ValueError):
            calculate_metrics(equity=[100.0, float("nan")])

        with self.assertRaises(ValueError):
            calculate_metrics(equity=[100.0, float("inf")])

        with self.assertRaises(ValueError):
            calculate_metrics(equity=[100.0, 110.0], periods_per_year=0)

        with self.assertRaises(ValueError):
            calculate_metrics(equity=[100.0, 110.0], periods_per_year=-252)

        with self.assertRaises(ValueError):
            calculate_metrics(equity=[100.0, 110.0], risk_free_rate=float("nan"))

        with self.assertRaises(ValueError):
            calculate_metrics(equity=[100.0, 110.0], trade_pnls=[10.0, float("nan")])


if __name__ == "__main__":
    unittest.main()

