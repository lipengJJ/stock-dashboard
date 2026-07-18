# 股票期权结构每日分析

工作目录：`/Users/lipeng01/vscode/stock-streamlit-dashboard`

你是股票期权结构分析自动化脚本。严格按以下步骤执行，不询问任何确认，直接完成所有操作。

---

## Step 0：读取配置（并行）

用 Read 工具**同时**读取：

1. `config/tickers.json` → 获取 `tickers`（标的列表）和 `expiry`（到期日）
2. `ai_prompt.md` → 作为分析背景参考

后续所有步骤以配置文件内容为准，不使用任何硬编码值。

---

## Step 1：并行采集全部 MCP 数据

根据 tickers 列表，**全部并行**调用以下工具（N 个标的共 1+N+N+N 个并行调用）：

1. `get_quotes` — tickers: 所有标的逗号拼接（如 `"KO,QQQ,SPY"`）
2. 每个 ticker 调用 `get_options_gex` — expiry: `<config.expiry>`, topRows: 15
3. 每个 ticker 调用 `get_options_dex` — expiry: `<config.expiry>`, topRows: 15
4. 每个 ticker 调用 `analyze_setup`

单个工具失败时记录错误继续执行，不中断整体流程。

---

## Step 2：整理数据，生成完整 JSON

将采集结果整理为以下结构：

```json
{
  "generated_at": "<当前 ISO 8601 时间>",
  "expiry": "<来自 config.expiry>",
  "tickers": {
    "<TICKER>": {
      "quote": {
        "price": 0.0,
        "change": 0.0,
        "change_pct": 0.0,
        "volume": 0,
        "updated": ""
      },
      "gex": {
        "spot": 0.0,
        "expiry": "",
        "net_gex": 0.0,
        "flip_level": 0.0,
        "max_gamma_strike": 0.0,
        "call_wall": 0.0,
        "put_wall": 0.0,
        "put_call_oi": 0.0,
        "put_call_vol": 0.0,
        "regime": "long|mixed|short",
        "strikes": [
          {
            "strike": 0.0,
            "call_gex": 0.0,
            "put_gex": 0.0,
            "total_gex": 0.0,
            "call_wall": false,
            "put_wall": false,
            "max_gamma": false
          }
        ]
      },
      "dex": {
        "net_dex": 0.0,
        "top_positive": null,
        "top_negative": null,
        "strikes": [
          {
            "strike": 0.0,
            "call_dex": 0.0,
            "put_dex": 0.0,
            "total_dex": 0.0
          }
        ]
      },
      "indicators": {
        "score": 0,
        "rsi": 0.0,
        "macd_hist": 0.0,
        "stoch_k": 0.0,
        "adx": 0.0,
        "sma50": 0.0,
        "sma200": 0.0,
        "bb_pb": 0.0,
        "bb_bandwidth": 0.0,
        "bb_upper": 0.0,
        "bb_lower": 0.0,
        "candle_latest": "",
        "candle_regime": ""
      },
      "setup": "<中文分析，见下方说明>"
    }
  }
}
```

### regime 判断规则
- `net_gex > 0` 且 `spot >= flip_level` → `"long"`
- `net_gex < 0` → `"short"`
- 其他 → `"mixed"`

### indicators 字段（从 analyze_setup JSON 输出中直接提取数值）

| indicators 字段 | analyze_setup 返回路径 |
|---|---|
| `score` | 顶部 Score 数值 |
| `rsi` | `rsi.latest.value` |
| `macd_hist` | `macd.latest.hist` |
| `stoch_k` | `stoch.latest.k` |
| `adx` | `adx.latest.adx` |
| `sma50` | `sma50.latest.value` |
| `sma200` | `sma200.latest.value` |
| `bb_pb` | `bbands.latest.pb` |
| `bb_bandwidth` | `bbands.latest.bandwidth` |
| `bb_upper` | `bbands.latest.upper` |
| `bb_lower` | `bbands.latest.lower` |
| `candle_latest` | `candles.latest` |
| `candle_regime` | `candles.regime` |

### setup 字段（中文分析，Markdown 格式，不超过 300 字）

严格按以下 6 点框架撰写，结合本次 GEX/DEX/indicators 数据：

1. **当前趋势**：SMA50/200 均线排列与量价关系
2. **关键价位**：Call Wall（阻力）/ Gamma Flip（分界）/ Put Wall（支撑）及其与现价距离
3. **指标信号**：RSI、MACD Hist、Stoch %K 综合读数
4. **近期形态**：布林带状态（是否 Squeeze）、最新蜡烛形态信号
5. **情景推演**：上行触发条件 + 下行触发条件（结合 regime 和 DEX 净方向）
6. **风险提示**：一句话标注当前最大风险点

末尾加一行评分：`📊 综合评分：🟢 +X 偏多 / ⚪ 中性 / 🔴 偏空`

---

## Step 3：写入文件

1. 用 Write 工具写入 `data/latest.json`
2. 用 Write 工具写入 `data/history/<YYYY-MM-DD_HH-MM>.json`（时间戳取自 `generated_at`）

---

## Step 4：Git 推送

```bash
cd /Users/lipeng01/vscode/stock-streamlit-dashboard
source .env 2>/dev/null || true
git config user.email "bot@stockdashboard.local"
git config user.name "StockBot"
git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"
git pull --rebase origin main 2>/dev/null || true
git add data/
git commit -m "data: $(date '+%Y-%m-%d %H:%M') | <各ticker价格及regime摘要>"
git push origin main && echo "✅ 推送成功" || echo "⚠️ 推送失败，数据已本地保存"
```

---

## Step 5：输出一行摘要

```
✅ 2026-07-17 22:45 | KO $81.56 🟢Long | QQQ $695.33 🔴Short | SPY $743.29 ⚠️Mixed | 已推送 GitHub
```

每个标的 regime 符号：🟢Long / 🔴Short / ⚠️Mixed
