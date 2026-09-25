"""Portfolio performance metrics calculations.

This module provides standard quantitative performance and risk metrics for
evaluating backtest equity curves and trading trade logs.
Built entirely using the Python standard library.

Conventions, Bankruptcy, and Edge Cases:
----------------------------------------
1. Equity Sequence & Return Periods:
   - The input `equity` sequence represents portfolio valuations over time,
     including the initial starting capital at index 0.
   - For an equity sequence of length N, there are N - 1 periodic returns:
         r_t = (equity[t] - equity[t-1]) / equity[t-1], for t = 1, ..., N-1.
   - If N == 1 (only starting capital is present), returns cannot be evaluated;
     total_return, cagr, max_drawdown, sharpe_ratio, sortino_ratio, and
     calmar_ratio return 0.0.

2. Invalid Negative and Non-Finite Inputs:
   - An empty `equity` sequence raises ValueError.
   - Any non-finite value (NaN, +Inf, -Inf) in `equity` or `trade_pnls`
     raises ValueError.
   - For long-only portfolios, negative equity is invalid and raises ValueError.
   - If starting equity is zero (`equity[0] == 0`) and any subsequent value is
     strictly positive, ValueError is raised (long-only capital cannot grow from zero).
   - `periods_per_year` must be an integer > 0; otherwise ValueError is raised.
   - `risk_free_rate` must be a finite number; otherwise ValueError is raised.

3. All-Zero Equity and Bankruptcy:
   - All-Zero Equity: If all equity values are zero (`equity[t] == 0` for all t),
     total_return, cagr, max_drawdown, sharpe_ratio, sortino_ratio, and
     calmar_ratio return 0.0. Trade statistics (win_rate, profit_loss_ratio)
     reflect the provided `trade_pnls` (or 0.0 if empty).
   - Bankruptcy occurs if portfolio equity drops to zero (`equity[t] == 0`)
     after starting with positive capital. In this case, total_return = -1.0,
     cagr = -1.0, and max_drawdown = 1.0 (100% loss).
   - Returns after equity reaches zero are treated as 0.0.

4. Zero Denominators and Infinite Ratios:
   - Sharpe Ratio:
     Annualized excess return divided by annualized sample standard deviation
     (ddof=1) of periodic returns.
     - If N - 1 < 2, sample standard deviation is undefined; returns 0.0.
     - If sample standard deviation is 0.0:
         returns +inf if mean excess return > 0,
         returns -inf if mean excess return < 0,
         returns 0.0 if mean excess return == 0.
   - Sortino Ratio:
     Annualized excess return divided by annualized downside deviation, where
     downside deviation = sqrt(mean(min(excess_t, 0)^2)) across all N - 1 periods.
     - If downside deviation is 0.0:
         returns +inf if mean excess return > 0,
         returns -inf if mean excess return < 0,
         returns 0.0 if mean excess return == 0.
   - Calmar Ratio:
     Defined as CAGR / max_drawdown.
     - If max_drawdown is 0.0:
         returns +inf if CAGR > 0,
         returns -inf if CAGR < 0,
         returns 0.0 if CAGR == 0.
   - Win Rate:
     Proportion of trades where PnL > 0.
     If trade_pnls is empty, win_rate is 0.0.
   - Profit-Loss Ratio:
     (mean of winning trades) / abs(mean of losing trades).
     - If no trades or all trades are zero: returns 0.0.
     - If winners exist but no losers: returns +inf.
     - If losers exist but no winners: returns 0.0.
"""

from collections.abc import Sequence
import math


def calculate_metrics(
    equity: Sequence[float],
    trade_pnls: Sequence[float] = (),
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> dict[str, float]:
    """Calculate portfolio performance and risk metrics.

    Args:
        equity: Sequence of portfolio equity values over time, including starting equity.
        trade_pnls: Sequence of realized trade PnL values.
        periods_per_year: Trading periods per year for annualization (default 252).
        risk_free_rate: Annualized risk-free rate (default 0.0).

    Returns:
        Dictionary with keys:
            - total_return: Cumulative return as a decimal fraction.
            - cagr: Compound Annual Growth Rate.
            - max_drawdown: Maximum peak-to-trough decline as a positive fraction.
            - win_rate: Fraction of winning trades (pnl > 0).
            - profit_loss_ratio: Average winning trade / abs(average losing trade).
            - sharpe_ratio: Annualized sample Sharpe ratio.
            - sortino_ratio: Annualized Sortino ratio with downside semivariance.
            - calmar_ratio: CAGR / max_drawdown.

    Raises:
        ValueError: If inputs contain non-finite numbers, invalid dimensions,
                    negative equity, zero initial equity that turns positive,
                    or non-positive periods_per_year.
    """
    # 1. Validation
    if not isinstance(equity, Sequence) or len(equity) == 0:
        raise ValueError("equity sequence must be a non-empty Sequence.")

    for idx, val in enumerate(equity):
        if not isinstance(val, (int, float)) or not math.isfinite(val):
            raise ValueError(f"equity contains non-finite or non-numeric value at index {idx}: {val}")
        if val < 0:
            raise ValueError(f"equity cannot contain negative values (long only), got {val} at index {idx}")

    if not isinstance(periods_per_year, int) or periods_per_year <= 0:
        raise ValueError(f"periods_per_year must be a positive integer, got: {periods_per_year}")

    if not isinstance(risk_free_rate, (int, float)) or not math.isfinite(risk_free_rate):
        raise ValueError(f"risk_free_rate must be a finite number, got: {risk_free_rate}")

    if not isinstance(trade_pnls, Sequence):
        raise ValueError("trade_pnls must be a Sequence.")

    for idx, pnl in enumerate(trade_pnls):
        if not isinstance(pnl, (int, float)) or not math.isfinite(pnl):
            raise ValueError(f"trade_pnls contains non-finite or non-numeric value at index {idx}: {pnl}")

    # Trade statistics: Win Rate & Profit-Loss Ratio
    num_trades = len(trade_pnls)
    if num_trades == 0:
        win_rate = 0.0
        profit_loss_ratio = 0.0
    else:
        winning_trades = [float(p) for p in trade_pnls if p > 0]
        losing_trades = [float(p) for p in trade_pnls if p < 0]

        win_rate = len(winning_trades) / float(num_trades)

        if len(winning_trades) == 0 and len(losing_trades) == 0:
            profit_loss_ratio = 0.0
        elif len(losing_trades) == 0:
            profit_loss_ratio = float("inf")
        elif len(winning_trades) == 0:
            profit_loss_ratio = 0.0
        else:
            mean_winner = sum(winning_trades) / len(winning_trades)
            mean_loser = sum(losing_trades) / len(losing_trades)
            profit_loss_ratio = mean_winner / abs(mean_loser)

    # 2. Check for zero initial equity
    starting_equity = float(equity[0])
    if starting_equity == 0.0:
        if any(v > 0 for v in equity):
            raise ValueError("equity starting at zero cannot become positive in a long-only portfolio")
        # All-zero equity: return zero metrics
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "max_drawdown": 0.0,
            "win_rate": win_rate,
            "profit_loss_ratio": profit_loss_ratio,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
        }

    n = len(equity)
    ending_equity = float(equity[-1])

    # 3. Total Return & Maximum Drawdown
    total_return = (ending_equity - starting_equity) / starting_equity

    max_drawdown = 0.0
    running_peak = starting_equity
    for val in equity:
        val_f = float(val)
        if val_f > running_peak:
            running_peak = val_f
        if running_peak > 0:
            dd = (running_peak - val_f) / running_peak
            if dd > max_drawdown:
                max_drawdown = dd

    # 4. CAGR
    num_returns = n - 1
    if num_returns == 0:
        cagr = 0.0
    elif ending_equity <= 0:
        # Bankruptcy convention
        cagr = -1.0
    else:
        years = num_returns / periods_per_year
        cagr = (ending_equity / starting_equity) ** (1.0 / years) - 1.0

    # 5. Periodic returns and Sharpe / Sortino Ratios
    if num_returns == 0:
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
    else:
        # Periodic returns (n-1 observations)
        periodic_returns: list[float] = []
        is_bankrupt = False
        for t in range(1, n):
            prev = float(equity[t - 1])
            curr = float(equity[t])
            if is_bankrupt or prev <= 0:
                is_bankrupt = True
                periodic_returns.append(0.0)
            else:
                r = (curr - prev) / prev
                periodic_returns.append(r)
                if curr <= 0:
                    is_bankrupt = True

        rf_period = float(risk_free_rate) / float(periods_per_year)
        excess_returns = [r - rf_period for r in periodic_returns]
        mean_excess = sum(excess_returns) / num_returns
        mean_return = sum(periodic_returns) / num_returns

        # Sharpe ratio: annualized sample stdev (ddof=1)
        if num_returns < 2:
            sharpe_ratio = 0.0
        else:
            variance = sum((r - mean_return) ** 2 for r in periodic_returns) / (num_returns - 1)
            sample_stdev = math.sqrt(variance)
            if sample_stdev == 0.0:
                if mean_excess > 0:
                    sharpe_ratio = float("inf")
                elif mean_excess < 0:
                    sharpe_ratio = float("-inf")
                else:
                    sharpe_ratio = 0.0
            else:
                sharpe_ratio = (mean_excess / sample_stdev) * math.sqrt(periods_per_year)

        # Sortino ratio: downside sqrt mean min(excess, 0)^2
        downside_squared_sum = sum(min(e, 0.0) ** 2 for e in excess_returns)
        downside_mean_sq = downside_squared_sum / num_returns
        downside_stdev = math.sqrt(downside_mean_sq)

        if downside_stdev == 0.0:
            if mean_excess > 0:
                sortino_ratio = float("inf")
            elif mean_excess < 0:
                sortino_ratio = float("-inf")
            else:
                sortino_ratio = 0.0
        else:
            sortino_ratio = (mean_excess / downside_stdev) * math.sqrt(periods_per_year)

    # 6. Calmar Ratio: cagr / max_drawdown
    if max_drawdown == 0.0:
        if cagr > 0:
            calmar_ratio = float("inf")
        elif cagr < 0:
            calmar_ratio = float("-inf")
        else:
            calmar_ratio = 0.0
    else:
        calmar_ratio = cagr / max_drawdown

    return {
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "profit_loss_ratio": profit_loss_ratio,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "calmar_ratio": calmar_ratio,
    }

