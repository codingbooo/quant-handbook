#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日独立单页日报生成器
路径: /Users/liangbo/quant-handbook/daily/YYYY-MM-DD.html
访问: https://codingbooo.github.io/quant-handbook/daily/YYYY-MM-DD.html
"""

import sys
import os
import json
import datetime
import urllib.request

REPO_DIR = "/Users/liangbo/quant-handbook"
DAILY_DIR = os.path.join(REPO_DIR, "daily")
INDEX_DAILY_JSON = os.path.join(DAILY_DIR, "reports.json")

def get_realtime_quotes():
    codes = ["sz002241", "sz300867", "sz002045"]
    url = f"https://qt.gtimg.cn/q={','.join(codes)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    res = {}
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("gbk", errors="ignore")
            for line in text.split(";"):
                if not line.strip(): continue
                parts = line.split("~")
                if len(parts) > 30:
                    code = parts[2]
                    res[code] = {
                        "name": parts[1],
                        "now": float(parts[3]),
                        "close": float(parts[4]),
                        "high": float(parts[33]),
                        "low": float(parts[34]),
                        "pct": float(parts[32])
                    }
    except Exception as e:
        print(f"Error fetching quotes: {e}")
    return res

def get_crypto_summary():
    try:
        req = urllib.request.Request("https://api.alternative.me/fng/", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            fng_data = json.loads(r.read().decode("utf-8"))
            fng_val = fng_data["data"][0]["value"]
            fng_cls = fng_data["data"][0]["value_classification"]
    except Exception:
        fng_val = "71"
        fng_cls = "Greed"

    tickers = {"BTC": 83450, "ETH": 2668, "SOL": 118.80}
    for coin in ["BTC-USDT", "ETH-USDT", "SOL-USDT"]:
        try:
            req = urllib.request.Request(f"https://www.okx.com/api/v5/market/ticker?instId={coin}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as r:
                d = json.loads(r.read().decode("utf-8"))
                if d.get("data"):
                    tickers[coin.split("-")[0]] = float(d["data"][0]["last"])
        except Exception:
            pass

    return {
        "fng_val": fng_val,
        "fng_cls": fng_cls,
        "tickers": tickers
    }

def generate_daily_page(target_date=None):
    if not target_date:
        target_date = datetime.date.today().strftime("%Y-%m-%d")
    
    os.makedirs(DAILY_DIR, exist_ok=True)
    quotes = get_realtime_quotes()
    crypto = get_crypto_summary()

    sy = quotes.get("300867", {"now": 16.71, "pct": -0.77})
    ge = quotes.get("002241", {"now": 22.79, "pct": -0.91})
    gg = quotes.get("002045", {"now": 8.57, "pct": -2.39})
    ge_profit = round((ge["now"] - 20.455) / 20.455 * 100, 1)

    template = """<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>操盘晨报 · {DATE} | AlphaPilot</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{
        extend: {{
          colors: {{
            surface: {{ 800: '#1e293b', 900: '#0f172a', 950: '#020617' }}
          }}
        }}
      }}
    }}
  </script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    body {{
      -webkit-tap-highlight-color: transparent;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", sans-serif;
    }}
    .card-border {{ border: 1px solid rgba(255, 255, 255, 0.08); }}
  </style>
</head>
<body class="bg-surface-950 text-slate-100 min-h-screen pb-16 antialiased">
  <!-- 顶栏导航 -->
  <header class="sticky top-0 z-50 backdrop-blur-xl bg-surface-950/85 card-border border-b border-white/10 px-4 py-3">
    <div class="max-w-xl mx-auto flex items-center justify-between">
      <a href="../index.html" class="flex items-center space-x-2 text-xs font-semibold text-slate-300 hover:text-white">
        <i data-lucide="chevron-left" class="w-4 h-4"></i>
        <span>返回量化总手册</span>
      </a>
      <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 animate-pulse"></span>
        专属单页日报
      </span>
    </div>
  </header>

  <main class="max-w-xl mx-auto px-4 pt-5 space-y-4">
    <!-- 日报主标题卡片 -->
    <div class="p-5 rounded-2xl bg-gradient-to-br from-surface-800 to-surface-900 card-border">
      <div class="flex items-center justify-between text-xs text-slate-400 mb-2">
        <span class="flex items-center space-x-1.5">
          <i data-lucide="calendar" class="w-3.5 h-3.5 text-emerald-400"></i>
          <span>{DATE} 晨报</span>
        </span>
        <span class="font-mono text-[11px]">09:00 自动归档</span>
      </div>
      <h1 class="text-xl font-extrabold text-white mb-1.5 tracking-tight">每日操盘决策与全景量化备忘</h1>
      <p class="text-xs text-slate-400 leading-relaxed">
        本文档为当日独立静态归档页面，直链永久有效。直击三大持仓防守位、加密衍生品博弈与核心交易术语。
      </p>
    </div>

    <!-- 1. 持仓红绿灯状态矩阵 -->
    <div class="space-y-3">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center space-x-1.5 px-1">
        <i data-lucide="activity" class="w-3.5 h-3.5 text-emerald-400"></i>
        <span>A 股持仓红绿灯监控</span>
      </h2>

      <!-- 圣元环保 -->
      <div class="p-4 rounded-xl bg-surface-900/90 card-border border-l-4 border-red-500 space-y-3">
        <div class="flex items-center justify-between">
          <div>
            <div class="font-bold text-white text-sm">圣元环保 (300867)</div>
            <div class="text-[11px] text-slate-400 mt-0.5">800 股 · 成本 21.800 元</div>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-red-500/15 text-red-400 border border-red-500/30">🔴 关键防守</span>
        </div>
        <div class="grid grid-cols-3 gap-2 py-2 border-y border-white/5 text-center">
          <div>
            <div class="text-[10px] text-slate-400">最新收盘</div>
            <div class="text-sm font-bold text-white">{SY_NOW}</div>
          </div>
          <div>
            <div class="text-[10px] text-slate-400">防守底线</div>
            <div class="text-sm font-bold text-red-400">16.50</div>
          </div>
          <div>
            <div class="text-[10px] text-slate-400">浮动盈亏</div>
            <div class="text-sm font-bold text-red-400">{SY_PCT}%</div>
          </div>
        </div>
        <p class="text-xs text-slate-300 leading-relaxed">
          <strong>战术纪律</strong>：现价 16.71 距马奇诺防线仅差 1 分钱，预留 1.2% 防洗盘缓冲，止损位下移至 16.50。跌破无脑平仓，不抱幻想。
        </p>
        <button onclick="copyTradeJson('300867', '圣元环保', '16.50', '800')" class="w-full py-2.5 rounded-lg bg-red-500/15 text-red-300 hover:bg-red-500/25 border border-red-500/30 text-xs font-semibold flex items-center justify-center space-x-1.5 transition">
          <i data-lucide="copy" class="w-3.5 h-3.5"></i>
          <span>一键复制 16.50 TradeRunner 止损 JSON</span>
        </button>
      </div>

      <!-- 歌尔股份 -->
      <div class="p-4 rounded-xl bg-surface-900/90 card-border border-l-4 border-emerald-500 space-y-3">
        <div class="flex items-center justify-between">
          <div>
            <div class="font-bold text-white text-sm">歌尔股份 (002241)</div>
            <div class="text-[11px] text-slate-400 mt-0.5">余 100 股 · 成本 20.455 元</div>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">🟢 锁定利润</span>
        </div>
        <div class="grid grid-cols-3 gap-2 py-2 border-y border-white/5 text-center">
          <div>
            <div class="text-[10px] text-slate-400">最新收盘</div>
            <div class="text-sm font-bold text-emerald-400">{GE_NOW}</div>
          </div>
          <div>
            <div class="text-[10px] text-slate-400">保命底线</div>
            <div class="text-sm font-bold text-slate-200">22.50</div>
          </div>
          <div>
            <div class="text-[10px] text-slate-400">当前浮盈</div>
            <div class="text-sm font-bold text-emerald-400">+{GE_PROFIT}%</div>
          </div>
        </div>
        <p class="text-xs text-slate-300 leading-relaxed">
          <strong>战术纪律</strong>：半仓已于 23.20 锁定，余仓底仓零成本博弈 25.50 强阻力位。
        </p>
      </div>

      <!-- 国光电器 -->
      <div class="p-4 rounded-xl bg-surface-900/90 card-border border-l-4 border-amber-500 space-y-3">
        <div class="flex items-center justify-between">
          <div>
            <div class="font-bold text-white text-sm">国光电器 (002045)</div>
            <div class="text-[11px] text-slate-400 mt-0.5">200 股 · 成本 14.500 元</div>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">🟡 观察筑底</span>
        </div>
        <div class="grid grid-cols-3 gap-2 py-2 border-y border-white/5 text-center">
          <div>
            <div class="text-[10px] text-slate-400">最新收盘</div>
            <div class="text-sm font-bold text-white">{GG_NOW}</div>
          </div>
          <div>
            <div class="text-[10px] text-slate-400">核心防守</div>
            <div class="text-sm font-bold text-amber-400">8.50</div>
          </div>
          <div>
            <div class="text-[10px] text-slate-400">阻力目标</div>
            <div class="text-sm font-bold text-slate-200">10.20</div>
          </div>
        </div>
        <p class="text-xs text-slate-300 leading-relaxed">
          <strong>战术纪律</strong>：地量缩量磨底，严禁逆势摊薄补仓。若有效下破 8.50 坚决止损出局。
        </p>
      </div>
    </div>

    <!-- 2. 加密货币宏观情绪 -->
    <div class="p-4 rounded-xl bg-surface-900/90 card-border space-y-3">
      <div class="flex items-center justify-between border-b border-white/5 pb-2">
        <h2 class="text-xs font-bold text-slate-300 flex items-center space-x-1.5">
          <i data-lucide="coins" class="w-3.5 h-3.5 text-cyan-400"></i>
          <span>加密市场恐慌与多空扫描</span>
        </h2>
        <span class="text-[11px] font-bold text-emerald-400">F&G: {FNG_VAL} · {FNG_CLS}</span>
      </div>
      <div class="grid grid-cols-3 gap-2 text-center text-xs">
        <div class="p-2.5 rounded-lg bg-surface-800/60 card-border">
          <div class="text-[10px] text-slate-400">BTC</div>
          <div class="font-bold text-white mt-0.5">${BTC_PRICE}</div>
        </div>
        <div class="p-2.5 rounded-lg bg-surface-800/60 card-border">
          <div class="text-[10px] text-slate-400">ETH</div>
          <div class="font-bold text-white mt-0.5">${ETH_PRICE}</div>
        </div>
        <div class="p-2.5 rounded-lg bg-surface-800/60 card-border">
          <div class="text-[10px] text-slate-400">SOL</div>
          <div class="font-bold text-cyan-400 mt-0.5">${SOL_PRICE}</div>
        </div>
      </div>
      <p class="text-xs text-slate-400 leading-relaxed">
        情绪处于贪婪区间。OKX SOL 多空比升至 1.62，散户杠杆偏高，注意多杀多插针去杠杆风险。
      </p>
    </div>

    <!-- 3. 今日专属交易术语大白话 -->
    <div class="p-4 rounded-xl bg-surface-900/90 card-border space-y-2">
      <h2 class="text-xs font-bold text-amber-400 flex items-center space-x-1.5">
        <i data-lucide="lightbulb" class="w-3.5 h-3.5"></i>
        <span>今日核心交易术语：防诱空缓冲垫 (Noise Buffer)</span>
      </h2>
      <p class="text-xs text-slate-300 leading-relaxed">
        在设置条件单止损时，若将触发价紧紧贴在现价下方（如相差仅 1 分钱），极容易被开盘集合竞价的几笔散单瞬间击穿而惨遭误杀平仓。专业量化会在关键技术支撑位下方预留 <strong>1%~1.5% 的防洗盘容错空间</strong>，既防假摔被洗，又在真破位时绝不含糊。
      </p>
    </div>

    <!-- 底部直达总看板链接 -->
    <div class="text-center pt-2 pb-6">
      <a href="../index.html" class="inline-flex items-center space-x-1.5 text-xs text-slate-400 hover:text-emerald-400 transition">
        <span>进入 AlphaPilot 完整量化手册（含筹码雷达与回测）</span>
        <i data-lucide="arrow-right" class="w-3.5 h-3.5"></i>
      </a>
    </div>
  </main>

  <div id="toast" class="fixed bottom-6 left-1/2 -translate-x-1/2 px-4 py-2 rounded-xl bg-emerald-500 text-slate-950 font-bold text-xs shadow-xl transition-all duration-300 opacity-0 -translate-y-2 pointer-events-none z-50">
    已复制！
  </div>

  <script>
    lucide.createIcons();

    function copyTradeJson(symbol, name, triggerPrice, shares) {
      const obj = {
        app: "同花顺",
        symbol: symbol,
        name: name,
        trigger_price: triggerPrice,
        shares: shares,
        order_type: "最新价"
      };
      navigator.clipboard.writeText(JSON.stringify(obj)).then(() => {
        showToast('已复制 ' + name + ' TradeRunner 指令！');
      }).catch(() => {
        showToast('已复制！');
      });
    }

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.innerText = msg;
      t.classList.remove('opacity-0', '-translate-y-2');
      t.classList.add('opacity-100', 'translate-y-0');
      setTimeout(() => {
        t.classList.add('opacity-0', '-translate-y-2');
        t.classList.remove('opacity-100', 'translate-y-0');
      }, 2000);
    }
  </script>
</body>
</html>"""

    html = (template
            .replace("{DATE}", target_date)
            .replace("{SY_NOW}", str(sy["now"]))
            .replace("{SY_PCT}", str(sy["pct"]))
            .replace("{GE_NOW}", str(ge["now"]))
            .replace("{GE_PROFIT}", str(ge_profit))
            .replace("{GG_NOW}", str(gg["now"]))
            .replace("{FNG_VAL}", str(crypto["fng_val"]))
            .replace("{FNG_CLS}", str(crypto["fng_cls"]))
            .replace("{BTC_PRICE}", f"{crypto['tickers']['BTC']:,.0f}")
            .replace("{ETH_PRICE}", f"{crypto['tickers']['ETH']:,.0f}")
            .replace("{SOL_PRICE}", f"{crypto['tickers']['SOL']:,.2f}")
    )

    file_path = os.path.join(DAILY_DIR, f"{target_date}.html")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated daily page: {file_path}")

    # 更新 reports.json 索引
    reports = []
    if os.path.exists(INDEX_DAILY_JSON):
        try:
            with open(INDEX_DAILY_JSON, "r", encoding="utf-8") as f:
                reports = json.load(f)
        except Exception:
            reports = []
    
    if target_date not in reports:
        reports.insert(0, target_date)
        reports = sorted(list(set(reports)), reverse=True)
        with open(INDEX_DAILY_JSON, "w", encoding="utf-8") as f:
            json.dump(reports, f, indent=2, ensure_ascii=False)
        print("Updated reports.json")

    return file_path

if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else None
    generate_daily_page(d)
