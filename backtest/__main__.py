"""Run all built-in strategies against three reproducible synthetic regimes."""
from .engine import BacktestEngine
from .market import generate_market_data
from .strategies import DualSMAStrategy, DynamicGridStrategy, TrailingStopATRStrategy


def main() -> None:
    """Print strategy outcomes; use fresh strategy instances for each run."""
    factories = [DualSMAStrategy, lambda: DynamicGridStrategy(floor_price=80, ceiling_price=120, grid_step=2),
                 TrailingStopATRStrategy]
    print(f'{"Regime":12} {"Strategy":25} {"Return":>9} {"Drawdown":>9} {"Exits":>7}')
    for regime in ('bull', 'bear', 'oscillating'):
        bars = generate_market_data(num_bars=504, regime=regime, seed=42)
        for factory in factories:
            strategy = factory()
            result = BacktestEngine().run(bars, strategy)
            print(f'{regime:12} {type(strategy).__name__:25} '
                  f'{result.metrics["total_return"]:9.2%} '
                  f'{result.metrics["max_drawdown"]:9.2%} {len(result.trades):7d}')


if __name__ == '__main__':
    main()
