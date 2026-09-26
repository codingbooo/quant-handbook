"""
Chip Distribution (CYQ) and Smart Money Order Flow Analysis Module.
Pure Python standard library implementation.
"""
from dataclasses import dataclass
import bisect
import math
from typing import List, Dict, Any, Optional

@dataclass
class ChipMetrics:
    symbol: str
    latest_close: float
    winner_rate: float          # 获利盘比例 (0.0 ~ 1.0)
    avg_cost: float             # 全市场平均筹码成本
    concentration_70: float     # 70% 筹码集中度 (越小越密集，< 0.08 为高度控盘)
    concentration_90: float     # 90% 筹码集中度
    chip_range_70: tuple        # (p15, p85)
    chip_range_90: tuple        # (p05, p95)
    resistance_level: float     # 上方主要筹码套牢阻力位
    support_level: float        # 下方主要筹码支撑位

def calculate_chip_distribution(klines: List[List[str]], num_bins: int = 150) -> ChipMetrics:
    """
    klines items: [date, open, close, high, low, volume, turnover_pct, ...]
    """
    if not klines:
        raise ValueError("klines cannot be empty")
        
    symbol = klines[0][0] if len(klines[0]) > 0 else "UNKNOWN"
    all_high = max(float(k[3]) for k in klines)
    all_low = min(float(k[4]) for k in klines)
    
    low_bound = all_low * 0.96
    high_bound = all_high * 1.04
    step = (high_bound - low_bound) / num_bins
    price_bins = [low_bound + i * step for i in range(num_bins)]
    
    chips = [0.0] * num_bins
    
    for k in klines:
        o, c, h, l = float(k[1]), float(k[2]), float(k[3]), float(k[4])
        # 换手率，若无或类型不符则默认 2.5%
        turnover = 0.025
        if len(k) > 6 and isinstance(k[6], (int, float, str)):
            try:
                val = float(k[6])
                if val > 0:
                    turnover = min(val / 100.0 if val > 1.0 else val, 0.5)
            except (ValueError, TypeError):
                turnover = 0.025
        
        # 历史筹码衰减 (换手率衰减模型)
        decay = 1.0 - turnover
        chips = [chip * decay for chip in chips]
        
        # 当日换手筹码按三角或均匀模型注入 [l, h]
        idx_low = bisect.bisect_left(price_bins, l)
        idx_high = bisect.bisect_left(price_bins, h)
        if idx_high <= idx_low:
            idx_high = idx_low + 1
        idx_high = min(idx_high, num_bins)
        
        slot_count = max(idx_high - idx_low, 1)
        added = turnover / slot_count
        for i in range(idx_low, idx_high):
            chips[i] += added
            
    total = sum(chips)
    if total > 0:
        chips = [c / total for c in chips]
        
    latest_close = float(klines[-1][2])
    win_idx = bisect.bisect_left(price_bins, latest_close)
    winner_rate = sum(chips[:win_idx])
    avg_cost = sum(p * c for p, c in zip(price_bins, chips))
    
    # 计算累计分布
    cumsum = []
    curr = 0.0
    for c in chips:
        curr += c
        cumsum.append(curr)
        
    def get_percentile_price(p: float) -> float:
        idx = bisect.bisect_left(cumsum, p)
        return price_bins[min(idx, num_bins - 1)]
        
    p05 = get_percentile_price(0.05)
    p95 = get_percentile_price(0.95)
    p15 = get_percentile_price(0.15)
    p85 = get_percentile_price(0.85)
    
    conc70 = (p85 - p15) / (p85 + p15) if (p85 + p15) > 0 else 0.0
    conc90 = (p95 - p05) / (p95 + p05) if (p95 + p05) > 0 else 0.0
    
    # 寻找套牢峰与支撑峰
    # 找到最大筹码峰
    max_chip_val = max(chips)
    peak_idx = chips.index(max_chip_val)
    peak_price = price_bins[peak_idx]
    
    # 上方套牢峰 (在当前收盘价上方、筹码相对密集的位置)
    upper_chips = [(chips[i], price_bins[i]) for i in range(win_idx, num_bins)]
    resistance = max(upper_chips, key=lambda x: x[0])[1] if upper_chips else latest_close * 1.1
    
    # 下方支撑峰
    lower_chips = [(chips[i], price_bins[i]) for i in range(0, win_idx)]
    support = max(lower_chips, key=lambda x: x[0])[1] if lower_chips else latest_close * 0.92
    
    return ChipMetrics(
        symbol=symbol,
        latest_close=latest_close,
        winner_rate=winner_rate,
        avg_cost=avg_cost,
        concentration_70=conc70,
        concentration_90=conc90,
        chip_range_70=(p15, p85),
        chip_range_90=(p05, p95),
        resistance_level=resistance,
        support_level=support
    )
