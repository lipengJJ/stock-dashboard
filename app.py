"""
Stock Options Dashboard — Streamlit Community Cloud
读取 data/latest.json（由 run_analysis.md 定时分析生成并推送），
展示 GEX / DEX / 技术指标 / 历史趋势。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── 页面配置 ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Options Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_FILE   = Path(__file__).parent / "data" / "latest.json"
HISTORY_DIR = Path(__file__).parent / "data" / "history"

TICKER_NAMES = {
    "KO":  "可口可乐 Coca-Cola",
    "QQQ": "纳斯达克 100 QQQ",
    "SPY": "标普 500 SPY",
}

REGIME_CFG = {
    "long":  ("🟢 Long Gamma",   "#2ea043", "#1a3d24"),
    "mixed": ("⚠️ Mixed / 临界", "#e3b341", "#3d3014"),
    "short": ("🔴 Short Gamma",  "#f85149", "#3d1a1a"),
}

BEAR_CANDLES = {"CDLENGULFING_BEAR", "CDLHARAMI_BEAR", "CDLSHOOTINGSTAR",
                "CDLEVENINGSTAR", "CDLDARKCLOUDCOVER"}
BULL_CANDLES = {"CDLHAMMER", "CDLENGULFING_BULL", "CDLHARAMI_BULL",
                "CDLMORNINGSTAR", "CDLPIERCING"}


# ── 数据加载 ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_data() -> dict:
    if not DATA_FILE.exists():
        return {}
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=1800)
def load_history() -> list[dict]:
    if not HISTORY_DIR.exists():
        return []
    rows = []
    for f in sorted(HISTORY_DIR.glob("*.json")):
        try:
            snap = json.loads(f.read_text(encoding="utf-8"))
            ts_str = snap.get("generated_at", "")
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            for ticker, td in snap.get("tickers", {}).items():
                quote = td.get("quote", {})
                gex   = td.get("gex", {})
                ind   = td.get("indicators", {})
                rows.append({
                    "time":       dt,
                    "ticker":     ticker,
                    "price":      quote.get("price") or gex.get("spot"),
                    "net_gex":    gex.get("net_gex"),
                    "flip_level": gex.get("flip_level"),
                    "regime":     gex.get("regime", "mixed"),
                    "rsi":        ind.get("rsi"),
                    "score":      ind.get("score"),
                })
        except Exception:
            continue
    return rows


# ── 规则引擎：从原始指标生成分析文字（零 token）────────────────────────────────
def generate_analysis(gex: dict, dex: dict, ind: dict) -> str:
    if not ind:
        return ""

    spot    = gex.get("spot", 0)
    regime  = gex.get("regime", "mixed")
    flip    = gex.get("flip_level")
    call_w  = gex.get("call_wall")
    put_w   = gex.get("put_wall")
    net_dex = dex.get("net_dex", 0)

    sma50  = ind.get("sma50", 0)
    sma200 = ind.get("sma200", 0)
    rsi    = ind.get("rsi")
    macd   = ind.get("macd_hist")
    stoch  = ind.get("stoch_k")
    adx    = ind.get("adx")
    bw     = ind.get("bb_bandwidth")
    candle = ind.get("candle_latest", "")
    c_reg  = ind.get("candle_regime", "")
    score  = ind.get("score", 0)

    lines = []

    # 1. 趋势
    if sma50 and sma200:
        if spot > sma50 > sma200:
            lines.append("1️⃣ **趋势**：黄金叉结构，中长期上升趋势完好")
        elif spot < sma200:
            lines.append("1️⃣ **趋势**：价格低于 SMA200，中长期偏弱")
        elif spot < sma50:
            lines.append("1️⃣ **趋势**：跌破 SMA50，短线偏弱，中期结构待确认")
        else:
            lines.append("1️⃣ **趋势**：均线混排，方向待定")

    # 2. 关键价位
    if call_w and put_w and flip:
        lines.append(
            f"2️⃣ **关键位**：阻力 **${call_w}**（Call Wall）"
            f" · 分界 **${flip}**（Gamma Flip）"
            f" · 支撑 **${put_w}**（Put Wall）"
        )

    # 3. 指标
    signals = []
    if rsi is not None:
        if rsi < 30:    signals.append(f"RSI {rsi:.0f} 超卖🟢")
        elif rsi > 70:  signals.append(f"RSI {rsi:.0f} 超买🔴")
        else:           signals.append(f"RSI {rsi:.0f} 中性⚪")
    if macd is not None:
        signals.append("MACD 多头🟢" if macd > 0 else "MACD 空头🔴")
    if stoch is not None:
        if stoch < 20:  signals.append(f"Stoch {stoch:.0f} 超卖区🟢")
        elif stoch > 80: signals.append(f"Stoch {stoch:.0f} 超买区🔴")
    if adx is not None:
        signals.append(f"ADX {adx:.0f} {'趋势明确' if adx > 25 else '无趋势'}")
    if signals:
        lines.append("3️⃣ **指标**：" + " · ".join(signals))

    # 4. 形态 / Squeeze
    form = []
    if bw is not None and bw < 5:
        form.append(f"BB Squeeze（带宽 {bw:.1f}%）突破临近⚡")
    if candle:
        if candle in BEAR_CANDLES or c_reg == "bearish_dominant":
            form.append(f"{candle} 看空形态🔴")
        elif candle in BULL_CANDLES:
            form.append(f"{candle} 看多形态🟢")
        else:
            form.append(candle)
    if form:
        lines.append("4️⃣ **形态**：" + " · ".join(form))

    # 5. 情景推演
    if regime == "long" and call_w and flip:
        lines.append(
            f"5️⃣ **情景**：Long Gamma，${flip}–${call_w} 区间振荡概率高。"
            f"突破 ${call_w} 看多；跌破 ${flip} 结构转弱。"
        )
    elif regime == "short" and flip:
        dex_note = "DEX 净空，下行压力大" if net_dex < 0 else "DEX 净多，下跌有托底"
        lines.append(
            f"5️⃣ **情景**：Short Gamma，波动放大风险高。{dex_note}。"
            f"收复 ${flip} 是结构改善信号。"
        )
    elif flip:
        lines.append(
            f"5️⃣ **情景**：Mixed 制度，${flip} 为多空分界线。"
            f"方向选择取决于能否有效突破该价位。"
        )

    # 6. 风险
    risks = []
    if bw is not None and bw < 4:
        risks.append("布林带极度压缩，突破时止损需收紧")
    if regime == "short":
        risks.append("Short Gamma 波动放大，方向性仓位谨慎")
    if rsi is not None and rsi > 68:
        risks.append(f"RSI {rsi:.0f} 偏高，追高风险大")
    if risks:
        lines.append("6️⃣ **风险**：" + "；".join(risks))

    score_e = "🟢" if score >= 2 else ("🔴" if score <= -2 else "⚪")
    lines.append(f"\n**📊 综合评分：{score_e} {score:+d}/10**（规则引擎，仅供参考）")

    return "\n\n".join(lines)


# ── 指标面板 ──────────────────────────────────────────────────────────────────
def render_indicators(ind: dict) -> None:
    if not ind:
        return

    score = ind.get("score", 0)
    rsi   = ind.get("rsi")
    macd  = ind.get("macd_hist")
    stoch = ind.get("stoch_k")
    adx   = ind.get("adx")
    bw    = ind.get("bb_bandwidth")

    score_e = "🟢" if score >= 2 else ("🔴" if score <= -2 else "⚪")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        st.metric("技术评分", f"{score_e} {score:+d}",
                  help="analyze_setup 综合技术评分（-10 ~ +10）")
    with c2:
        if rsi is not None:
            label = "超卖" if rsi < 30 else ("超买" if rsi > 70 else "中性")
            st.metric("RSI(14)", f"{rsi:.1f}", delta=label,
                      delta_color="normal" if rsi < 50 else "inverse")
    with c3:
        if macd is not None:
            st.metric("MACD Hist", f"{macd:+.2f}",
                      delta="多头" if macd > 0 else "空头",
                      delta_color="normal" if macd > 0 else "inverse")
    with c4:
        if stoch is not None:
            st.metric("Stoch %K", f"{stoch:.1f}", help="< 20 超卖 · > 80 超买")
    with c5:
        if adx is not None:
            st.metric("ADX(14)", f"{adx:.1f}",
                      help="< 20 无趋势 · > 25 趋势明确")
    with c6:
        if bw is not None:
            squeeze = bw < 5
            st.metric("BB 带宽", f"{bw:.1f}%",
                      delta="⚡ Squeeze" if squeeze else None,
                      delta_color="off" if not squeeze else "inverse",
                      help="< 5% 极度压缩，方向性突破临近")


# ── 辅助函数 ──────────────────────────────────────────────────────────────────
def regime_label(gex: dict) -> tuple[str, str, str]:
    net  = gex.get("net_gex", 0)
    flip = gex.get("flip_level", 0)
    spot = gex.get("spot", 0)
    if net > 0 and spot >= flip:
        return REGIME_CFG["long"]
    if net < 0:
        return REGIME_CFG["short"]
    return REGIME_CFG["mixed"]


def data_age_minutes(generated_at: str) -> float | None:
    try:
        dt = datetime.fromisoformat(generated_at)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return (datetime.utcnow() - dt).total_seconds() / 60
    except Exception:
        return None


# ── GEX 柱状图 ────────────────────────────────────────────────────────────────
def gex_bar_chart(ticker: str, gex: dict, spot: float) -> go.Figure | None:
    strikes_raw = gex.get("strikes", [])
    if not strikes_raw:
        return None

    strikes = [s["strike"] for s in strikes_raw]
    totals  = [s.get("total_gex", 0) for s in strikes_raw]
    colors  = ["#3fb950" if v >= 0 else "#f85149" for v in totals]
    labels  = [
        f"<b>${s['strike']}</b>"
        + (" | Call Wall" if s.get("call_wall") else "")
        + (" | Put Wall"  if s.get("put_wall")  else "")
        + (" | Max γ"     if s.get("max_gamma") else "")
        for s in strikes_raw
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=strikes, y=totals,
        marker_color=colors,
        text=[f"{v/1e6:.2f}M" if abs(v) >= 1e6 else f"{v/1e3:.0f}K" for v in totals],
        textposition="outside",
        hovertext=labels, hoverinfo="text+y",
        name="GEX",
    ))
    fig.add_vline(x=spot, line_dash="dash", line_color="#e3b341", line_width=2,
                  annotation_text=f" Spot ${spot:.2f}", annotation_font_color="#e3b341",
                  annotation_position="top right")
    flip = gex.get("flip_level")
    if flip:
        fig.add_vline(x=flip, line_dash="dot", line_color="#8b949e", line_width=1,
                      annotation_text=f" Flip ${flip}", annotation_font_color="#8b949e",
                      annotation_position="bottom right")
    fig.update_layout(
        title=dict(text=f"{ticker} · GEX by Strike（到期 {gex.get('expiry','')}）",
                   font_size=14, font_color="#e6edf3"),
        xaxis=dict(title="Strike", color="#8b949e", gridcolor="#30363d"),
        yaxis=dict(title="GEX ($)", color="#8b949e", gridcolor="#30363d", tickformat=".2s"),
        plot_bgcolor="#0d1117", paper_bgcolor="#161b22", font_color="#e6edf3",
        showlegend=False, margin=dict(l=10, r=10, t=40, b=10), height=320,
    )
    return fig


# ── DEX 柱状图 ────────────────────────────────────────────────────────────────
def dex_bar_chart(ticker: str, dex: dict, spot: float) -> go.Figure | None:
    strikes_raw = dex.get("strikes", [])
    if not strikes_raw:
        return None

    strikes = [s["strike"] for s in strikes_raw]
    totals  = [s.get("total_dex", 0) for s in strikes_raw]
    colors  = ["#58a6ff" if v >= 0 else "#f85149" for v in totals]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=strikes, y=totals, marker_color=colors,
        text=[f"{v/1e9:.2f}B" if abs(v) >= 1e9
              else f"{v/1e6:.1f}M" if abs(v) >= 1e6
              else f"{v/1e3:.0f}K" for v in totals],
        textposition="outside", name="DEX",
    ))
    fig.add_vline(x=spot, line_dash="dash", line_color="#e3b341", line_width=2,
                  annotation_text=f" Spot ${spot:.2f}", annotation_font_color="#e3b341")
    fig.update_layout(
        title=dict(text=f"{ticker} · DEX by Strike", font_size=14, font_color="#e6edf3"),
        xaxis=dict(title="Strike", color="#8b949e", gridcolor="#30363d"),
        yaxis=dict(title="DEX ($)", color="#8b949e", gridcolor="#30363d", tickformat=".2s"),
        plot_bgcolor="#0d1117", paper_bgcolor="#161b22", font_color="#e6edf3",
        showlegend=False, margin=dict(l=10, r=10, t=40, b=10), height=280,
    )
    return fig


# ── 关键价格层级 ──────────────────────────────────────────────────────────────
def render_levels(spot: float, gex: dict) -> None:
    rows = []
    for label, key in [("🟠 Call Wall（阻力）", "call_wall"),
                        ("🔶 Max Gamma（磁力）", "max_gamma_strike"),
                        ("⚡ Gamma Flip",        "flip_level"),
                        ("🔵 Put Wall（支撑）",   "put_wall")]:
        val = gex.get(key)
        if val:
            diff = (val - spot) / spot * 100
            rows.append((label, f"${val}", f"{diff:+.1f}%"))
    rows.insert(2, ("⭐ 现价 Spot", f"${spot:.2f}", "—"))
    st.dataframe(
        pd.DataFrame(rows, columns=["层级", "价格", "距现价"]),
        use_container_width=True, hide_index=True,
    )


# ── GEX/DEX 指标行 ────────────────────────────────────────────────────────────
def render_gex_metrics(gex: dict, dex: dict) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    net_gex = gex.get("net_gex", 0)
    net_dex = dex.get("net_dex", 0)

    with c1:
        st.metric("Net GEX",
                  f"{net_gex/1e6:.2f}M" if abs(net_gex) >= 1e6 else f"{net_gex/1e3:.0f}K",
                  delta="Long" if net_gex > 0 else "Short",
                  delta_color="normal" if net_gex > 0 else "inverse")
    with c2:
        st.metric("Gamma Flip", f"${gex.get('flip_level', '—')}")
    with c3:
        st.metric("Net DEX",
                  f"{net_dex/1e9:.2f}B" if abs(net_dex) >= 1e9
                  else f"{net_dex/1e6:.0f}M",
                  delta="做市商净多" if net_dex > 0 else "做市商净空",
                  delta_color="normal" if net_dex > 0 else "inverse")
    with c4:
        pcr_oi = gex.get("put_call_oi")
        st.metric("P/C OI", f"{pcr_oi:.2f}" if pcr_oi else "—",
                  help="< 0.7 偏多 | > 1.3 偏空")
    with c5:
        pcr_vol = gex.get("put_call_vol")
        st.metric("P/C Volume", f"{pcr_vol:.2f}" if pcr_vol else "—",
                  help="日内 Put/Call 成交量比")


# ── 单个 Ticker 完整分析 ──────────────────────────────────────────────────────
def render_ticker(ticker: str, data: dict) -> None:
    if not data:
        st.info(
            f"**{ticker}** 暂无数据。请在 Claude Code 中运行 `run_analysis.md` 生成最新数据。",
            icon="⏳",
        )
        return

    quote = data.get("quote", {})
    gex   = data.get("gex", {})
    dex   = data.get("dex", {})
    ind   = data.get("indicators", {})
    setup = data.get("setup", "")

    spot = quote.get("price") or gex.get("spot", 0)

    # ── 顶部价格 + regime badge ──
    col_left, col_right = st.columns([3, 1])
    with col_left:
        change     = quote.get("change", 0)
        change_pct = quote.get("change_pct", 0)
        color_str  = "#3fb950" if change >= 0 else "#f85149"
        arrow      = "▲" if change >= 0 else "▼"
        st.markdown(
            f"### ${spot:.2f} "
            f"<span style='color:{color_str};font-size:18px'>"
            f"{arrow} {change:+.2f} ({change_pct:+.2f}%)</span>",
            unsafe_allow_html=True,
        )
        vol = quote.get("volume", 0)
        if vol:
            st.caption(f"成交量：{vol:,.0f} · 数据时间：{quote.get('updated', '—')}")
    with col_right:
        label, fg, bg = regime_label(gex)
        st.markdown(
            f"<div style='background:{bg};border:1px solid {fg};border-radius:8px;"
            f"padding:10px 14px;text-align:center;color:{fg};font-weight:700;font-size:14px'>"
            f"{label}</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── GEX/DEX 核心指标行 ──
    render_gex_metrics(gex, dex)

    # ── 技术指标行（来自 indicators 字段）──
    if ind:
        st.markdown("**── 技术指标**")
        render_indicators(ind)

    st.divider()

    # ── 图表 + 关键价位 ──
    col_chart, col_levels = st.columns([3, 1])
    with col_chart:
        tab_gex, tab_dex = st.tabs(["📊 GEX 分布", "📈 DEX 分布"])
        with tab_gex:
            fig = gex_bar_chart(ticker, gex, spot)
            st.plotly_chart(fig, use_container_width=True) if fig else st.info("GEX 数据暂无")
        with tab_dex:
            fig2 = dex_bar_chart(ticker, dex, spot)
            st.plotly_chart(fig2, use_container_width=True) if fig2 else st.info("DEX 数据暂无")
    with col_levels:
        st.markdown("**关键价格层级**")
        if spot:
            render_levels(spot, gex)

    st.divider()

    # ── 分析文字：优先 Claude 生成的 setup，fallback 规则引擎 ──
    if setup:
        with st.expander("🏦 机构行为解读 & 操作建议（Claude 生成）", expanded=True):
            st.markdown(setup)
    elif ind:
        with st.expander("🤖 技术分析摘要（规则引擎）", expanded=True):
            st.markdown(generate_analysis(gex, dex, ind))

    # ── 仓位快速参考 ──
    call_wall = gex.get("call_wall")
    put_wall  = gex.get("put_wall")
    flip      = gex.get("flip_level")
    if call_wall and put_wall and flip and spot:
        with st.expander("📋 仓位管理快速参考", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**✅ 持仓目标**")
                t1 = call_wall * 1.03
                t2 = call_wall * 1.06
                st.markdown(f"- 止盈 T1：**${t1:.2f}**（+{(t1-spot)/spot*100:.1f}%）")
                st.markdown(f"- 止盈 T2：**${t2:.2f}**（+{(t2-spot)/spot*100:.1f}%）")
                st.markdown(f"- 止损线：**${flip:.2f}**（Gamma Flip）")
            with c2:
                st.markdown("**💵 候场买入区**")
                st.markdown(f"- 第一买入区：**${call_wall*0.97:.2f} – ${call_wall*0.99:.2f}**")
                st.markdown(f"- Put Wall 区：**${put_wall:.2f} – ${put_wall*1.02:.2f}**")
                st.markdown(f"- 止损参考：**${flip:.2f}**")


# ── 历史趋势 ──────────────────────────────────────────────────────────────────
def render_history() -> None:
    rows = load_history()
    if len(rows) < 2:
        st.info("历史数据不足 2 条，每次执行分析任务自动追加一条快照。", icon="⏳")
        return

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time")
    tickers = sorted(df["ticker"].unique())

    st.markdown("#### 价格走势")
    fig_price = go.Figure()
    for t in tickers:
        tdf = df[df["ticker"] == t].dropna(subset=["price"])
        fig_price.add_trace(go.Scatter(
            x=tdf["time"], y=tdf["price"],
            mode="lines+markers", name=t, line=dict(width=2),
        ))
    fig_price.update_layout(
        plot_bgcolor="#0d1117", paper_bgcolor="#161b22", font_color="#e6edf3",
        xaxis=dict(color="#8b949e", gridcolor="#30363d"),
        yaxis=dict(color="#8b949e", gridcolor="#30363d"),
        legend=dict(bgcolor="#161b22", bordercolor="#30363d"),
        margin=dict(l=10, r=10, t=10, b=10), height=280,
    )
    st.plotly_chart(fig_price, use_container_width=True)

    st.markdown("#### Net GEX 趋势（M）")
    fig_gex = go.Figure()
    for t in tickers:
        tdf = df[df["ticker"] == t].dropna(subset=["net_gex"])
        fig_gex.add_trace(go.Bar(x=tdf["time"], y=tdf["net_gex"] / 1e6, name=t))
    fig_gex.update_layout(
        barmode="group",
        plot_bgcolor="#0d1117", paper_bgcolor="#161b22", font_color="#e6edf3",
        xaxis=dict(color="#8b949e", gridcolor="#30363d"),
        yaxis=dict(title="Net GEX (M)", color="#8b949e", gridcolor="#30363d"),
        legend=dict(bgcolor="#161b22", bordercolor="#30363d"),
        margin=dict(l=10, r=10, t=10, b=10), height=260,
    )
    st.plotly_chart(fig_gex, use_container_width=True)

    # RSI 趋势（如果有 indicators 数据）
    if df["rsi"].notna().any():
        st.markdown("#### RSI(14) 趋势")
        fig_rsi = go.Figure()
        for t in tickers:
            tdf = df[df["ticker"] == t].dropna(subset=["rsi"])
            if tdf.empty:
                continue
            fig_rsi.add_trace(go.Scatter(
                x=tdf["time"], y=tdf["rsi"],
                mode="lines+markers", name=t, line=dict(width=2),
            ))
        fig_rsi.add_hline(y=70, line_dash="dot", line_color="#f85149",
                          annotation_text="超买 70", annotation_font_color="#f85149")
        fig_rsi.add_hline(y=30, line_dash="dot", line_color="#3fb950",
                          annotation_text="超卖 30", annotation_font_color="#3fb950")
        fig_rsi.update_layout(
            plot_bgcolor="#0d1117", paper_bgcolor="#161b22", font_color="#e6edf3",
            xaxis=dict(color="#8b949e", gridcolor="#30363d"),
            yaxis=dict(title="RSI", color="#8b949e", gridcolor="#30363d", range=[0, 100]),
            legend=dict(bgcolor="#161b22", bordercolor="#30363d"),
            margin=dict(l=10, r=10, t=10, b=10), height=240,
        )
        st.plotly_chart(fig_rsi, use_container_width=True)

    st.markdown("#### Regime 变化记录")
    REGIME_EMOJI = {"long": "🟢 Long", "short": "🔴 Short", "mixed": "⚠️ Mixed"}
    pivot = (
        df.pivot_table(index="time", columns="ticker", values="regime", aggfunc="last")
          .sort_index(ascending=False)
    )
    pivot.index = pivot.index.strftime("%Y-%m-%d %H:%M")
    pivot = pivot.map(lambda v: REGIME_EMOJI.get(str(v).lower(), v) if pd.notna(v) else "—")
    st.dataframe(pivot, use_container_width=True)


# ── 侧边栏 ────────────────────────────────────────────────────────────────────
def render_sidebar(data: dict) -> str:
    st.sidebar.title("📊 Stock Dashboard")
    st.sidebar.markdown("---")

    generated_at = data.get("generated_at", "")
    expiry       = data.get("expiry", "—")

    if generated_at:
        try:
            ts  = datetime.fromisoformat(generated_at)
            age = data_age_minutes(generated_at)
            st.sidebar.success(f"数据更新：{ts.strftime('%Y-%m-%d %H:%M')} UTC")
            if age is not None:
                if age > 1440:
                    st.sidebar.warning(f"⚠️ 数据已 {age/60:.0f} 小时未更新")
                elif age > 480:
                    st.sidebar.info(f"ℹ️ 数据更新于 {age/60:.1f} 小时前")
        except Exception:
            st.sidebar.info(f"数据时间：{generated_at}")
    else:
        st.sidebar.warning("暂无数据，请执行 run_analysis.md")

    st.sidebar.markdown(f"**到期日：** `{expiry}`")
    st.sidebar.markdown("---")

    tickers  = list(data.get("tickers", {}).keys()) or list(TICKER_NAMES.keys())
    selected = st.sidebar.radio(
        "选择标的",
        tickers,
        format_func=lambda t: f"{t} · {TICKER_NAMES.get(t, t)}",
    )

    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 刷新数据", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "数据由 Claude Code + Stocks Intelligence MCP 生成\n\n"
        "运行 `run_analysis.md` 更新，非实时报价"
    )
    return selected


# ── 主入口 ────────────────────────────────────────────────────────────────────
def main() -> None:
    data     = load_data()
    selected = render_sidebar(data)

    tab_now, tab_hist = st.tabs(["📊 当前分析", "📈 历史趋势"])

    with tab_now:
        st.title(f"📊 {selected} · {TICKER_NAMES.get(selected, '')} 期权结构分析")
        st.caption(
            f"GEX / DEX · Dealer Positioning · 到期日 {data.get('expiry', '—')} · "
            "数据由 Stocks Intelligence MCP 采集"
        )
        tickers_data = data.get("tickers", {})
        render_ticker(selected, tickers_data.get(selected, {}))

        # 底部全标的概览
        if len(tickers_data) > 1:
            st.divider()
            st.subheader("📋 全标的概览")
            cols = st.columns(len(tickers_data))
            for col, (t, td) in zip(cols, tickers_data.items()):
                with col:
                    q    = td.get("quote", {})
                    gex  = td.get("gex",   {})
                    ind  = td.get("indicators", {})
                    spot = q.get("price") or gex.get("spot", 0)
                    label, fg, bg = regime_label(gex)
                    chg  = q.get("change_pct", 0)
                    score = ind.get("score")
                    score_e = ("🟢" if score >= 2 else "🔴" if score <= -2 else "⚪") if score is not None else ""
                    st.markdown(
                        f"<div style='background:#161b22;border:1px solid #30363d;"
                        f"border-radius:10px;padding:14px;text-align:center'>"
                        f"<div style='font-size:16px;font-weight:700'>{t}</div>"
                        f"<div style='font-size:22px;font-weight:700;margin:4px 0'>${spot:.2f}</div>"
                        f"<div style='color:{'#3fb950' if chg>=0 else '#f85149'};font-size:13px'>"
                        f"{'▲' if chg>=0 else '▼'} {chg:+.2f}%</div>"
                        f"<div style='margin-top:6px;font-size:11px;background:{bg};"
                        f"color:{fg};border-radius:12px;padding:3px 8px'>{label}</div>"
                        + (f"<div style='margin-top:4px;font-size:11px;color:#8b949e'>"
                           f"技术 {score_e} {score:+d}</div>" if score is not None else "")
                        + "</div>",
                        unsafe_allow_html=True,
                    )

    with tab_hist:
        st.title("📈 历史趋势")
        st.caption("每次执行分析任务自动追加一条快照，按时间展示价格、GEX 和 Regime 变化")
        render_history()


if __name__ == "__main__":
    main()
