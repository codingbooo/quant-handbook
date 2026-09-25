"""Unit tests for backtest.market."""

import datetime
import unittest

from backtest.market import (
    Bar,
    MarketRegime,
    SyntheticMarketGenerator,
    generate_market_data,
)


class TestMarketGenerator(unittest.TestCase):
    def test_bar_fields_and_defaults(self):
        d = datetime.date(2023, 1, 3)
        b = Bar(
            date=d,
            open=10.0,
            high=10.5,
            low=9.8,
            close=10.2,
            volume=1000,
        )
        self.assertEqual(b.date, d)
        self.assertEqual(b.open, 10.0)
        self.assertEqual(b.high, 10.5)
        self.assertEqual(b.low, 9.8)
        self.assertEqual(b.close, 10.2)
        self.assertEqual(b.volume, 1000)
        self.assertEqual(b.symbol, "SYNTH")
        self.assertIsNone(b.limit_up)
        self.assertIsNone(b.limit_down)

    def test_zero_num_bars(self):
        bars = generate_market_data(num_bars=0)
        self.assertEqual(bars, [])

    def test_weekday_dates_only(self):
        # 100 trading days starting from a Friday
        bars = generate_market_data(
            num_bars=100,
            start_date=datetime.date(2023, 1, 6),  # 2023-01-06 is Friday
            seed=42,
        )
        self.assertEqual(len(bars), 100)
        for i, bar in enumerate(bars):
            # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
            self.assertLess(
                bar.date.weekday(),
                5,
                f"Bar at index {i} on {bar.date} is not a weekday (weekday={bar.date.weekday()})",
            )
            if i > 0:
                self.assertGreater(bar.date, bars[i - 1].date)

    def test_weekend_start_date_advances_to_weekday(self):
        # 2023-01-07 is Saturday; should advance to Monday 2023-01-09
        bars = generate_market_data(
            num_bars=5,
            start_date="2023-01-07",
            seed=42,
        )
        self.assertEqual(bars[0].date, datetime.date(2023, 1, 9))
        self.assertEqual(bars[0].date.weekday(), 0)  # Monday

    def test_lot_friendly_volumes(self):
        bars = generate_market_data(num_bars=100, seed=123)
        for bar in bars:
            self.assertIsInstance(bar.volume, int)
            self.assertEqual(bar.volume % 100, 0, f"Volume {bar.volume} is not a multiple of 100")
            self.assertGreaterEqual(bar.volume, 100)

    def test_price_limits_standard_10_percent(self):
        init_price = 50.0
        bars = generate_market_data(
            num_bars=60,
            initial_price=init_price,
            daily_limit_pct=0.10,
            seed=999,
        )

        prev_close = init_price
        for i, bar in enumerate(bars):
            expected_up = round(prev_close * 1.10, 2)
            expected_down = round(prev_close * 0.90, 2)

            self.assertAlmostEqual(bar.limit_up, expected_up, places=2)
            self.assertAlmostEqual(bar.limit_down, expected_down, places=2)

            # Check that prices strictly stay within daily limits
            self.assertGreaterEqual(bar.open, bar.limit_down - 1e-6)
            self.assertLessEqual(bar.open, bar.limit_up + 1e-6)

            self.assertGreaterEqual(bar.high, bar.limit_down - 1e-6)
            self.assertLessEqual(bar.high, bar.limit_up + 1e-6)

            self.assertGreaterEqual(bar.low, bar.limit_down - 1e-6)
            self.assertLessEqual(bar.low, bar.limit_up + 1e-6)

            self.assertGreaterEqual(bar.close, bar.limit_down - 1e-6)
            self.assertLessEqual(bar.close, bar.limit_up + 1e-6)

            prev_close = bar.close

    def test_no_daily_limits(self):
        bars = generate_market_data(
            num_bars=30,
            daily_limit_pct=None,
            seed=42,
        )
        for bar in bars:
            self.assertIsNone(bar.limit_up)
            self.assertIsNone(bar.limit_down)

    def test_ohlc_consistency_and_precision(self):
        bars = generate_market_data(num_bars=150, seed=777)
        for bar in bars:
            # Low is <= open and close
            self.assertLessEqual(bar.low, min(bar.open, bar.close) + 1e-6)
            # High is >= open and close
            self.assertGreaterEqual(bar.high, max(bar.open, bar.close) - 1e-6)
            # Low <= High
            self.assertLessEqual(bar.low, bar.high)
            # Positive prices
            self.assertGreater(bar.low, 0.0)
            # Rounding to 2 decimal places
            self.assertEqual(round(bar.open, 2), bar.open)
            self.assertEqual(round(bar.high, 2), bar.high)
            self.assertEqual(round(bar.low, 2), bar.low)
            self.assertEqual(round(bar.close, 2), bar.close)

    def test_seed_reproducibility(self):
        bars_1 = generate_market_data(num_bars=50, seed=12345)
        bars_2 = generate_market_data(num_bars=50, seed=12345)
        bars_3 = generate_market_data(num_bars=50, seed=54321)

        for b1, b2 in zip(bars_1, bars_2):
            self.assertEqual(b1.date, b2.date)
            self.assertEqual(b1.open, b2.open)
            self.assertEqual(b1.high, b2.high)
            self.assertEqual(b1.low, b2.low)
            self.assertEqual(b1.close, b2.close)
            self.assertEqual(b1.volume, b2.volume)

        closes_1 = [b.close for b in bars_1]
        closes_3 = [b.close for b in bars_3]
        self.assertNotEqual(closes_1, closes_3)

    def test_regime_dynamics(self):
        # 1. Bull regime: positive trend over 252 bars
        bull_bars = generate_market_data(
            num_bars=252,
            initial_price=100.0,
            regime=MarketRegime.BULL,
            seed=101,
        )
        self.assertGreater(bull_bars[-1].close, bull_bars[0].close)

        # 2. Bear regime: negative trend over 252 bars
        bear_bars = generate_market_data(
            num_bars=252,
            initial_price=100.0,
            regime=MarketRegime.BEAR,
            seed=202,
        )
        self.assertLess(bear_bars[-1].close, bear_bars[0].close)

        # 3. Oscillating regime: stays centered near initial_price
        osc_bars = generate_market_data(
            num_bars=500,
            initial_price=100.0,
            regime=MarketRegime.OSCILLATING,
            seed=303,
        )
        closes = [b.close for b in osc_bars]
        mean_close = sum(closes) / len(closes)
        self.assertAlmostEqual(mean_close, 100.0, delta=15.0)

    def test_generator_class_interface(self):
        gen = SyntheticMarketGenerator(seed=42, symbol="600519")
        bars = gen.generate(num_bars=10)
        self.assertEqual(len(bars), 10)
        self.assertEqual(bars[0].symbol, "600519")

    def test_tightened_validation_initial_price(self):
        gen = SyntheticMarketGenerator(seed=42)
        with self.assertRaises(ValueError):
            gen.generate(initial_price=0.0)  # below 0.01

        with self.assertRaises(ValueError):
            gen.generate(initial_price=0.005)  # below 0.01

        with self.assertRaises(ValueError):
            gen.generate(initial_price=-10.0)

        with self.assertRaises(ValueError):
            gen.generate(initial_price=float("nan"))

        with self.assertRaises(ValueError):
            gen.generate(initial_price=float("inf"))

        # Valid edge price: exactly 0.01
        bars = gen.generate(num_bars=2, initial_price=0.01)
        self.assertEqual(len(bars), 2)

    def test_tightened_validation_daily_limit(self):
        # 0 < limit < 1 or None
        with self.assertRaises(ValueError):
            SyntheticMarketGenerator(daily_limit_pct=0.0)

        with self.assertRaises(ValueError):
            SyntheticMarketGenerator(daily_limit_pct=1.0)

        with self.assertRaises(ValueError):
            SyntheticMarketGenerator(daily_limit_pct=1.5)

        with self.assertRaises(ValueError):
            SyntheticMarketGenerator(daily_limit_pct=-0.10)

        with self.assertRaises(ValueError):
            SyntheticMarketGenerator(daily_limit_pct=float("nan"))

        # In generate() override
        gen = SyntheticMarketGenerator()
        with self.assertRaises(ValueError):
            gen.generate(daily_limit_pct=0.0)

        with self.assertRaises(ValueError):
            gen.generate(daily_limit_pct=1.0)

    def test_tightened_validation_volatility_and_drift(self):
        gen = SyntheticMarketGenerator()
        with self.assertRaises(ValueError):
            gen.generate(volatility=-0.01)

        with self.assertRaises(ValueError):
            gen.generate(volatility=float("nan"))

        with self.assertRaises(ValueError):
            gen.generate(drift=float("inf"))

        with self.assertRaises(ValueError):
            gen.generate(drift=float("nan"))

        # volatility == 0 is valid (non-negative)
        bars = gen.generate(num_bars=2, volatility=0.0, drift=0.0)
        self.assertEqual(len(bars), 2)

    def test_tightened_validation_base_volume(self):
        with self.assertRaises(ValueError):
            SyntheticMarketGenerator(base_volume=0)

        with self.assertRaises(ValueError):
            SyntheticMarketGenerator(base_volume=-100)

        with self.assertRaises(ValueError):
            SyntheticMarketGenerator(base_volume=100.5)  # type: ignore

        with self.assertRaises(ValueError):
            SyntheticMarketGenerator(base_volume=True)  # type: ignore

    def test_tightened_validation_num_bars(self):
        gen = SyntheticMarketGenerator()
        with self.assertRaises(ValueError):
            gen.generate(num_bars=-1)

        with self.assertRaises(ValueError):
            gen.generate(num_bars=10.5)  # type: ignore

        with self.assertRaises(ValueError):
            gen.generate(num_bars=True)  # type: ignore

    def test_illustrative_label_in_docstrings(self):
        import backtest.market as market_module

        self.assertIn("illustrative", market_module.__doc__.lower())
        self.assertIn("illustrative", SyntheticMarketGenerator.__doc__.lower())
        self.assertIn("illustrative", generate_market_data.__doc__.lower())


if __name__ == "__main__":
    unittest.main()

