"""Dependency-free quantitative trading simulation components."""
from .models import Bar, Order, OrderStatus, OrderType, Side, Trade
from .portfolio import Portfolio
from .execution import Broker, CommissionModel, SlippageModel
from .engine import BacktestEngine, BacktestResult, Strategy
from .metrics import calculate_metrics
from .market import MarketRegime, SyntheticMarketGenerator, generate_market_data
from .strategies import DualSMAStrategy, DynamicGridStrategy, TrailingStopATRStrategy

__all__ = ['Bar', 'Order', 'OrderStatus', 'OrderType', 'Side', 'Trade',
           'Portfolio', 'Broker', 'CommissionModel', 'SlippageModel',
           'BacktestEngine', 'BacktestResult', 'Strategy', 'calculate_metrics',
           'MarketRegime', 'SyntheticMarketGenerator', 'generate_market_data',
           'DualSMAStrategy', 'DynamicGridStrategy', 'TrailingStopATRStrategy']
