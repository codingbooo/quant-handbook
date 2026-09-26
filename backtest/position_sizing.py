"""
Dynamic Position Sizing & Portfolio Risk Allocation Engine.
(考虑整体账户仓位上限、单笔 1% 风险倒推模型、极精选 2~3 只持仓约束)
"""
from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class PositionPlan:
    symbol: str
    name: str
    buy_price: float
    stop_loss_price: float
    risk_distance_pct: float     # 止损幅度 (例如 4.5%)
    target_price: float
    payoff_ratio: float          # 盈亏比 (例如 3.2 : 1)
    allocated_shares: int        # 建议买入股数 (必须是 100 股整数倍)
    allocated_capital: float     # 建议买入资金 (元)
    position_pct_of_total: float # 占总资产比例 (例如 20.0%)
    max_portfolio_loss: float    # 若触发止损，对整体账户的最大净回撤金额 (严格等于总资产 * risk_budget_pct)
    overall_portfolio_status: str # 整体仓位健康度评估

class PortfolioRiskManager:
    def __init__(
        self,
        total_equity: float = 300000.0,    # 账户总资金 (默认 30 万)
        current_invested: float = 0.0,     # 当前已占用持仓金额
        market_regime: str = "NEUTRAL",    # 大盘环境: BULL / NEUTRAL / BEAR_DEFENSE
        risk_budget_per_trade: float = 0.015 # 单笔最大容忍回撤 (1.5% 总本金)
    ):
        self.total_equity = total_equity
        self.current_invested = current_invested
        self.market_regime = market_regime
        self.risk_budget_per_trade = risk_budget_per_trade

        # 根据大盘环境确定整体账户总仓位天花板
        if market_regime == "BULL":
            self.max_total_exposure = 0.85
        elif market_regime == "NEUTRAL":
            self.max_total_exposure = 0.40
        else:
            self.max_total_exposure = 0.15 # 熊市/熔断期总仓位严控在 15% 以下

    def calculate_position(
        self,
        symbol: str,
        name: str,
        buy_price: float,
        stop_loss_price: float,
        target_price: float,
        max_stock_cap: float = 0.30
    ) -> PositionPlan:
        if buy_price <= 0 or stop_loss_price >= buy_price:
            raise ValueError("止损价必须严格低于买入价且大于0")

        risk_distance = buy_price - stop_loss_price
        risk_distance_pct = risk_distance / buy_price
        reward_distance = target_price - buy_price
        payoff_ratio = reward_distance / risk_distance if risk_distance > 0 else 0.0

        # 1. 单笔风险金额上限 = 总资产 * 1.5%
        max_allowed_loss_amount = self.total_equity * self.risk_budget_per_trade

        # 2. 根据止损幅度倒推理论买入金额: 金额 * risk_distance_pct <= max_allowed_loss_amount
        theoretical_capital = max_allowed_loss_amount / risk_distance_pct

        # 3. 受限于单票最大持仓上限 (例如 30%)
        stock_cap_capital = self.total_equity * max_stock_cap
        capped_capital = min(theoretical_capital, stock_cap_capital)

        # 4. 受限于整体账户剩余可用安全仓位
        available_portfolio_room = max(0.0, (self.total_equity * self.max_total_exposure) - self.current_invested)
        final_capital = min(capped_capital, available_portfolio_room)

        # 5. 折算成整手 (100 股)
        shares = int(final_capital / buy_price // 100 * 100)
        actual_capital = shares * buy_price
        actual_position_pct = actual_capital / self.total_equity if self.total_equity > 0 else 0.0
        actual_max_loss = shares * risk_distance

        status_msg = f"大盘处于 {self.market_regime} 状态，账户总仓位上限被限制在 {self.max_total_exposure*100:.0f}%。"
        if available_portfolio_room <= 0:
            status_msg += " ⚠️ 当前仓位已达上限，禁止新增买入！"
        else:
            status_msg += f" 本次建议配置 {actual_position_pct*100:.1f}% 仓位，止损仅回撤本金 {actual_max_loss/self.total_equity*100:.2f}%。"

        return PositionPlan(
            symbol=symbol,
            name=name,
            buy_price=buy_price,
            stop_loss_price=stop_loss_price,
            risk_distance_pct=round(risk_distance_pct * 100, 2),
            target_price=target_price,
            payoff_ratio=round(payoff_ratio, 2),
            allocated_shares=shares,
            allocated_capital=round(actual_capital, 2),
            position_pct_of_total=round(actual_position_pct * 100, 2),
            max_portfolio_loss=round(actual_max_loss, 2),
            overall_portfolio_status=status_msg
        )
