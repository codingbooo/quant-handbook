"""
Market Regime and Macro Timing Filter Module (大盘系统性择时与流动性熔断网).
Based on index trend alignment (MA20/MA60) and market volume expansion.
"""
from dataclasses import dataclass
from typing import List, Dict, Optional
import bisect

@dataclass
class MarketRegimeState:
    date: str
    index_close: float
    ma20: float
    ma60: float
    regime: str           # "BULL" (进攻), "NEUTRAL" (震荡/减仓), "BEAR_DEFENSE" (空仓熔断)
    exposure_cap: float   # 允许的最大总仓位比例: BULL -> 1.0, NEUTRAL -> 0.35, BEAR_DEFENSE -> 0.0
    reason: str

class MarketRegimeFilter:
    def __init__(self, index_klines: List[List[str]]):
        """
        index_klines: [[date, open, close, high, low, volume, ...], ...]
        """
        self.history = index_klines
        self._states: Dict[str, MarketRegimeState] = {}
        self._compute_regimes()

    def _compute_regimes(self):
        closes = [float(k[2]) for k in self.history]
        dates = [k[0] for k in self.history]
        volumes = [float(k[5]) for k in self.history]

        for i in range(len(self.history)):
            curr_date = dates[i]
            curr_close = closes[i]

            if i < 20:
                self._states[curr_date] = MarketRegimeState(
                    date=curr_date, index_close=curr_close, ma20=curr_close, ma60=curr_close,
                    regime="NEUTRAL", exposure_cap=0.35, reason="数据预热中"
                )
                continue

            ma20 = sum(closes[i-19:i+1]) / 20.0
            ma60 = sum(closes[max(0, i-59):i+1]) / min(i+1, 60)
            vol_avg20 = sum(volumes[i-19:i+1]) / 20.0
            curr_vol = volumes[i]

            # 判定逻辑:
            # 1. 熊市熔断 (BEAR_DEFENSE): 价格低于 MA20 且 MA20 向下或跌破 MA60
            if curr_close < ma20 and (curr_close < ma60 or ma20 < ma60):
                self._states[curr_date] = MarketRegimeState(
                    date=curr_date, index_close=curr_close, ma20=ma20, ma60=ma60,
                    regime="BEAR_DEFENSE", exposure_cap=0.0,
                    reason="大盘跌破MA20/MA60生命线，系统性风险空仓防守"
                )
            # 2. 牛市进攻 (BULL): 价格稳居 MA20 之上，且 MA20 > MA60，量能健康
            elif curr_close >= ma20 and ma20 >= ma60 and curr_vol >= vol_avg20 * 0.8:
                self._states[curr_date] = MarketRegimeState(
                    date=curr_date, index_close=curr_close, ma20=ma20, ma60=ma60,
                    regime="BULL", exposure_cap=1.0,
                    reason="大盘多头排列且成交量健康，全开选股进攻"
                )
            # 3. 震荡整理 (NEUTRAL): 震荡或缩量，防守型轻仓
            else:
                self._states[curr_date] = MarketRegimeState(
                    date=curr_date, index_close=curr_close, ma20=ma20, ma60=ma60,
                    regime="NEUTRAL", exposure_cap=0.35,
                    reason="大盘处于均线纠缠或缩量震荡，严格限制仓位"
                )

    def get_state(self, date: str) -> MarketRegimeState:
        if date in self._states:
            return self._states[date]
        # 若找不到该日期，取最近的历史状态
        all_dates = sorted(self._states.keys())
        idx = bisect.bisect_right(all_dates, date) - 1
        if idx >= 0:
            return self._states[all_dates[idx]]
        return MarketRegimeState(date=date, index_close=0, ma20=0, ma60=0, regime="NEUTRAL", exposure_cap=0.35, reason="默认状态")
