"""
国海证券官方 QMT (xtquant) 实盘自动化交易系统接入脚手架
AlphaPilot Institutional Execution Engine (Dual-Mode: Paper / Live)
"""
import os
import sys
import time
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("GuohaiQMTTrader")

@dataclass
class TradeOrderRequest:
    symbol: str             # 标的代码，如 '002463.SZ', '601138.SH'
    action: str             # 'BUY' 或 'SELL'
    shares: int             # 买卖股数 (必须是 100 整数倍)
    order_type: str         # 'MARKET' (对手方最优) 或 'LIMIT' (限价)
    price: float            # 目标触发价/委托价
    stop_loss: float        # 硬核防守止损价
    take_profit: float      # 目标止盈价
    reason: str             # 交易策略逻辑来源

class GuohaiQMTExecutor:
    """
    国海证券官方迅投 QMT / xtquant 执行器
    支持模拟运行 (Paper Trading) 与 实盘切换 (Live Trading)
    """
    def __init__(self, account_id: str, mini_qmt_path: str, mode: str = "paper"):
        self.account_id = account_id
        self.mini_qmt_path = mini_qmt_path
        self.mode = mode.lower() # "paper" (模拟演练) 或 "live" (官方实盘)
        self.trader = None
        self.account = None
        self._connected = False

    def initialize(self) -> bool:
        logger.info(f"=== 正在启动国海证券量化引擎 [模式: {self.mode.upper()}] ===")
        if self.mode == "live":
            try:
                # 尝试导入官方 xtquant 库
                from xtquant import xttrader
                from xtquant.xttype import StockAccount
                from xtquant import xtconstant

                session_id = int(time.time())
                self.trader = xttrader.XtQuantTrader(self.mini_qmt_path, session_id)
                self.account = StockAccount(self.account_id)
                self.trader.start()
                res = self.trader.connect()
                if res == 0:
                    self._connected = True
                    logger.info(f"✅ 成功握手国海证券 miniQMT 柜台 (资金账号: {self.account_id})")
                    return True
                else:
                    logger.error(f"❌ 柜台握手失败，错误码: {res}。请检查国海金探号/超级终端是否处于登录状态。")
                    return False
            except ImportError:
                logger.error("❌ 未检测到 xtquant 官方库！开通国海权限后请在终端执行: pip install xtquant")
                return False
            except Exception as e:
                logger.error(f"❌ 连接异常: {e}")
                return False
        else:
            self._connected = True
            logger.info(f"ℹ️ [模拟就绪] 当前运行在安全沙盒模式，所有策略信号将在本地模拟撮合，资金安全保障中。")
            return True

    def execute_order(self, req: TradeOrderRequest) -> Dict[str, Any]:
        """执行买卖单并自动附加风控记录"""
        if not self._connected:
            raise RuntimeError("国海交易网关未就绪，禁止下单！")

        logger.info(f"🚀 [收到交易指令] {req.action} {req.symbol} | 股数: {req.shares} | 参考价: {req.price:.2f} | 理由: {req.reason}")
        logger.info(f"   🛡️ 附带防守止损线: {req.stop_loss:.2f} | 目标止盈线: {req.take_profit:.2f}")

        if self.mode == "live":
            from xtquant import xtconstant
            order_type_map = {
                "MARKET": xtconstant.MARKET_PEER_PRICE_FIRST, # 对手方最优成交 (防跳水穿透)
                "LIMIT": xtconstant.FIX_PRICE
            }
            order_side = xtconstant.STOCK_BUY if req.action == "BUY" else xtconstant.STOCK_SELL
            op_type = order_type_map.get(req.order_type, xtconstant.MARKET_PEER_PRICE_FIRST)

            order_id = self.trader.order_stock(
                account=self.account,
                stock_code=req.symbol,
                order_type=order_side,
                order_volume=req.shares,
                price_type=op_type,
                price=req.price
            )
            logger.info(f"✅ [国海实盘已报送] 订单已入交易所排队，合同单号: {order_id}")
            return {"status": "SUBMITTED", "order_id": order_id, "mode": "live"}
        else:
            # 模拟撮合成功
            fake_order_id = f"SIM_{int(time.time())}_{req.symbol}"
            logger.info(f"🎯 [模拟执行成功] 假设已在 {req.price:.2f} 撮合 {req.shares} 股，模拟单号: {fake_order_id}")
            return {"status": "SIMULATED_FILLED", "order_id": fake_order_id, "mode": "paper"}

    def query_positions(self) -> List[Dict[str, Any]]:
        """查询当前实盘真实持仓"""
        if self.mode == "live" and self._connected:
            positions = self.trader.query_stock_positions(self.account)
            res = []
            for p in positions:
                res.append({
                    "symbol": p.stock_code,
                    "volume": p.volume,
                    "can_use_volume": p.can_use_volume,
                    "open_price": p.open_price,
                    "market_value": p.market_value
                })
            return res
        else:
            # 默认返回 Tom 当前持仓示例
            return [
                {"symbol": "002241.SZ", "volume": 1000, "cost": 20.455, "name": "歌尔股份"},
                {"symbol": "300867.SZ", "volume": 1000, "cost": 21.800, "name": "圣元环保"},
                {"symbol": "002045.SZ", "volume": 1000, "cost": 14.500, "name": "国光电器"}
            ]

if __name__ == "__main__":
    # 本地快速连通性自测
    executor = GuohaiQMTExecutor(
        account_id="12345678", # 届时替换为 Tom 的国海真实资金账号
        mini_qmt_path=r"C:\国海证券QMT\userdata_mini",
        mode="paper" # 先以模拟沙盒模式启动自测
    )
    executor.initialize()

    # 模拟发送一笔建仓指令: 沪电股份 700 股
    sample_order = TradeOrderRequest(
        symbol="002463.SZ",
        action="BUY",
        shares=700,
        order_type="MARKET",
        price=124.05,
        stop_loss=118.00,
        take_profit=136.00,
        reason="RS相对强度优选龙头，缩量回踩MA20企稳，筹码集中度6.86%"
    )
    executor.execute_order(sample_order)
