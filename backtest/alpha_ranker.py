"""
Alpha Ranker & Ultra-Concentrated Quality Scorer (极精选战备池综合评分器).
Philosophy: "少而精，宁缺毋滥，只做主线最强龙头".
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class QualityScore:
    symbol: str
    name: str
    total_score: float         # 0 ~ 100 分
    rs_rating: float           # 相对大盘强度 (0~100)
    chip_score: float          # 筹码集中与获利分 (0~100)
    momentum_score: float      # 量价多头动能分 (0~100)
    verdict: str               # "强烈推荐 (Tier 1 绝对龙头)", "观察池", "坚决剔除"
    key_advantage: str
    suggested_position_cap: float # 建议单票最大仓位上限 (例如 0.25 即 25%)

def compute_relative_strength(stock_closes: List[float], benchmark_closes: List[float], period: int = 60) -> float:
    """
    计算相对基准的超额表现 (O'Neil RS 衍生算法)
    """
    if len(stock_closes) < period or len(benchmark_closes) < period:
        return 50.0
    stock_perf = (stock_closes[-1] - stock_closes[-period]) / stock_closes[-period]
    bench_perf = (benchmark_closes[-1] - benchmark_closes[-period]) / benchmark_closes[-period]
    alpha = stock_perf - bench_perf
    # 归一化到 0~100 评分
    score = 50.0 + (alpha * 100.0)
    return max(5.0, min(99.0, score))

def evaluate_stock_quality(
    symbol: str,
    name: str,
    stock_klines: List[List[str]],
    benchmark_klines: List[List[str]],
    chip_metrics: Any
) -> QualityScore:
    stock_closes = [float(k[2]) for k in stock_klines]
    bench_closes = [float(k[2]) for k in benchmark_klines]

    # 1. 相对强度分 (RS Rating)
    rs_short = compute_relative_strength(stock_closes, bench_closes, period=20)
    rs_mid = compute_relative_strength(stock_closes, bench_closes, period=60)
    rs_rating = rs_short * 0.4 + rs_mid * 0.6

    # 2. 筹码质量分 (Chip Score)
    # 获利盘高 + 集中度高（数值小）得分高
    conc = chip_metrics.concentration_70
    win_rate = chip_metrics.winner_rate
    # 集中度 < 8% 为满分基准
    conc_factor = max(0.0, min(1.0, (0.12 - conc) / 0.08)) if conc > 0 else 0.5
    chip_score = win_rate * 50.0 + conc_factor * 50.0

    # 3. 量价多头动能分 (Momentum Score)
    curr_close = stock_closes[-1]
    ma5 = sum(stock_closes[-5:]) / 5.0
    ma20 = sum(stock_closes[-20:]) / 20.0
    ma60 = sum(stock_closes[-min(len(stock_closes), 60):]) / min(len(stock_closes), 60)
    
    momentum = 50.0
    if curr_close > ma20 > ma60:
        momentum += 30.0
    if ma5 > ma20:
        momentum += 15.0
    if curr_close < ma60:
        momentum -= 35.0
    momentum_score = max(5.0, min(98.0, momentum))

    # 综合总分权重: RS 35% + 筹码 35% + 动能 30%
    total_score = rs_rating * 0.35 + chip_score * 0.35 + momentum_score * 0.30

    if total_score >= 75.0 and rs_rating >= 70.0 and chip_metrics.winner_rate >= 0.40:
        verdict = "强烈推荐 (Tier 1 核心龙头)"
        suggested_position_cap = 0.30 # 最多允许配 30%
        key_advantage = "相对大盘显著超额强势，主力高度控盘，右侧多头发散"
    elif total_score >= 60.0:
        verdict = "战备观察池 (等待回踩确认)"
        suggested_position_cap = 0.15 # 最多轻仓 15%
        key_advantage = "具备局部动能，但上方有一定筹码沉淀或相对强度不够极致"
    else:
        verdict = "坚决剔除 (劣质/跟跌弱势股)"
        suggested_position_cap = 0.0
        key_advantage = "落后于大盘，套牢盘沉重或走势破位，严禁买入"

    return QualityScore(
        symbol=symbol,
        name=name,
        total_score=round(total_score, 1),
        rs_rating=round(rs_rating, 1),
        chip_score=round(chip_score, 1),
        momentum_score=round(momentum_score, 1),
        verdict=verdict,
        key_advantage=key_advantage,
        suggested_position_cap=suggested_position_cap
    )
