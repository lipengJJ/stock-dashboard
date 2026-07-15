"""
Stock Options Dashboard — Streamlit Community Cloud
读取 data/latest.json（由 Claude Code 定时任务生成并推送），
展示 GEX / DEX 结构分析、关键价格层级和仓位建议。
"""
from __future__ import annotations

import json
from datetime import datetime
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

DATA_FILE    = Path(__file__).parent / "data" / "latest.json"
HISTORY_DIR  = Path(__file__).parent / "data" / "history"

TICKER_NAMES = {
    "KO":  "可口可乐 Coca-Cola",
    "QQQ": "纳斯达克 100 QQQ",
    "SPY": "标普 500 SPY",
}

REGIME_CONFIG = {
    "long":  ("🟢 Long Gamma",  "#2ea043", "#1a3d24"),
    "mixed": ("⚠️ Mixed / 临界", "#e3b341", "#3d3014"),
    "short": ("🔴 Short Gamma", "#f85149", "#3d1a1a"),
}


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
            with open(f, encoding="utf-8") as fh:
                snap = json.load(fh)
            ts_str = snap.get("generated_at", "")
            try:
                dt = datetime.fromisoformat(ts_str)
            except Exception:
                continue
            for ticker, td in snap.get("tickers", {}).items():
                quote = td.get("quote", {})
                gex   = td.get("gex",   {})
                rows.append({
                    "time":       dt,
                    "ticker":     ticker,
                    "price":      quote.get("price") or gex.get("spot"),
                    "net_gex":    gex.get("net_gex"),
                    "flip_level": gex.get("flip_level"),
                    "regime":     gex.get("regime", "mixed"),
                })
        except Exception:
            continue
    return rows


def regime_label(gex: dict) -> tuple[str, str, str]:
    """返回 (label, fg_color, bg_color)。"""
    net = gex.get("net_gex", 0)
    flip = gex.get("flip_level", 0)
    spot = gex.get("spot", 0)
    if net > 0 and spot >= flip:
        return REGIME_CONFIG["long"]
    if net < 0:
        return REGIME_CONFIG["short"]
    return REGIME_CONFIG["mixed"]


# ── 图表：GEX 柱状图 ──────────────────────────────────────────────────────────
def gex_bar_chart(ticker: str, gex: dict, spot: float) -> go.Figure:
    strikes_raw = gex.get("strikes", [])
    if not strikes_raw:
        return None

    strikes = [s.get("strike") for s in strikes_raw]
    totals  = [s.get("total_gex", 0) for s in strikes_raw]
    colors  = ["#3fb950" if v >= 0 else "#f85149" for v in totals]
    labels  = [
        f"<b>{s.get('strike')}</b><br>{'Call Wall' if s.get('call_wall') else ''}"
        f"{'Put Wall' if s.get('put_wall') else ''}"
        f"{'Max γ' if s.get('max_gamma') else ''}"
        for s in strikes_raw
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=strikes,
        y=totals,
        marker_color=colors,
        text=[f"{v/1e6:.2f}M" if abs(v) >= 1e6 else f"{v/1e3:.0f}K" for v in totals],
        textposition="outside",
        hovertext=labels,
        hoverinfo="text+y",
        name="GEX",
    ))
    # 现价竖线
    fig.add_vline(
        x=spot, line_dash="dash", line_color="#e3b341", line_width=2,
        annotation_text=f" Spot ${spot:.2f}", annotation_font_color="#e3b341",
        annotation_position="top right",
    )
    # flip 线
    flip = gex.get("flip_level")
    if flip:
        fig.add_vline(
            x=flip, line_dash="dot", line_color="#8b949e", line_width=1,
            annotation_text=f" Flip ${flip}", annotation_font_color="#8b949e",
            annotation_position="bottom right",
        )
    fig.update_layout(
        title=dict(text=f"{ticker} · GEX by Strike (到期 {gex.get('expiry', '')})",
                   font_size=14, font_color="#e6edf3"),
        xaxis=dict(title="Strike", color="#8b949e", gridcolor="#30363d"),
        yaxis=dict(title="GEX ($)", color="#8b949e", gridcolor="#30363d",
                   tickformat=".2s"),
        plot_bgcolor="#0d1117",
        paper_bgcolor="#161b22",
        font_color="#e6edf3",
        showlegend=False,
        margin=dict(l=10, r=10, t=40, b=10),
        height=320,
    )
    return fig


# ── 图表：DEX 柱状图 ──────────────────────────────────────────────────────────
def dex_bar_chart(ticker: str, dex: dict, spot: float) -> go.Figure:
    strikes_raw = dex.get("strikes", [])
    if not strikes_raw:
        return None

    strikes = [s.get("strike") for s in strikes_raw]
    totals  = [s.get("total_dex", 0) for s in strikes_raw]
    colors  = ["#58a6ff" if v >= 0 else "#f85149" for v in totals]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=strikes,
        y=totals,
        marker_color=colors,
        text=[f"{v/1e6:.1f}M" if abs(v) >= 1e6 else f"{v/1e3:.0f}K" for v in totals],
        textposition="outside",
        name="DEX",
    ))
    fig.add_vline(
        x=spot, line_dash="dash", line_color="#e3b341", line_width=2,
        annotation_text=f" Spot ${spot:.2f}", annotation_font_color="#e3b341",
    )
    fig.update_layout(
        title=dict(text=f"{ticker} · DEX by Strike", font_size=14, font_color="#e6edf3"),
        xaxis=dict(title="Strike", color="#8b949e", gridcolor="#30363d"),
        yaxis=dict(title="DEX ($)", color="#8b949e", gridcolor="#30363d",
                   tickformat=".2s"),
        plot_bgcolor="#0d1117",
        paper_bgcolor="#161b22",
        font_color="#e6edf3",
        showlegend=False,
        margin=dict(l=10, r=10, t=40, b=10),
        height=280,
    )
    return fig


# ── 关键价格层级表格 ──────────────────────────────────────────────────────────
def render_levels(spot: float, gex: dict) -> None:
    flip      = gex.get("flip_level")
    call_wall = gex.get("call_wall")
    put_wall  = gex.get("put_wall")
    max_gamma = gex.get("max_gamma_strike")

    levels = []
    if call_wall:
        diff = (call_wall - spot) / spot * 100
        levels.append(("🟠 Call Wall (阻力)", f"${call_wall}", f"{diff:+.1f}%",
                       "red" if diff < 0 else "green"))
    if max_gamma:
        diff = (max_gamma - spot) / spot * 100
        levels.append(("🔶 Max Gamma (磁力)", f"${max_gamma}", f"{diff:+.1f}%", "orange"))
    levels.append(("⭐ 现价 Spot", f"${spot:.2f}", "—", "yellow"))
    if flip:
        diff = (flip - spot) / spot * 100
        levels.append(("⚡ Gamma Flip", f"${flip}", f"{diff:+.1f}%",
                       "red" if flip < spot else "green"))
    if put_wall:
        diff = (put_wall - spot) / spot * 100
        levels.append(("🔵 Put Wall (支撑)", f"${put_wall}", f"{diff:+.1f}%", "blue"))

    df = pd.DataFrame(levels, columns=["层级", "价格", "距现价", "方向"])
    st.dataframe(df, use_container_width=True, hide_index=True)


# ── 指标卡片 ──────────────────────────────────────────────────────────────────
def metric_row(gex: dict, dex: dict, pcr_oi: float | None, pcr_vol: float | None) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    net_gex = gex.get("net_gex", 0)
    with c1:
        st.metric("Net GEX",
                  f"{net_gex/1e6:.2f}M" if abs(net_gex) >= 1e6 else f"{net_gex/1e3:.0f}K",
                  delta="Long" if net_gex > 0 else "Short",
                  delta_color="normal" if net_gex > 0 else "inverse")
    with c2:
        flip = gex.get("flip_level")
        st.metric("Gamma Flip", f"${flip}" if flip else "—")
    with c3:
        net_dex = dex.get("net_dex", 0)
        st.metric("Net DEX",
                  f"{net_dex/1e9:.2f}B" if abs(net_dex) >= 1e9
                  else f"{net_dex/1e6:.0f}M",
                  delta="做市商净多" if net_dex > 0 else "做市商净空",
                  delta_color="normal" if net_dex > 0 else "inverse")
    with c4:
        st.metric("P/C OI", f"{pcr_oi:.2f}" if pcr_oi else "—",
                  help="< 0.7 偏多 | > 1.3 偏空")
    with c5:
        st.metric("P/C Volume", f"{pcr_vol:.2f}" if pcr_vol else "—",
                  help="日内 Put 成交 / Call 成交")


# ── 无数据占位 ────────────────────────────────────────────────────────────────
def no_data_placeholder(ticker: str) -> None:
    st.info(
        f"**{ticker}** 暂无数据 — 定时任务尚未运行或数据文件未更新。\n\n"
        "请在 Claude Code 中手动触发一次分析，或等待下一次定时任务执行。",
        icon="⏳",
    )


# ── 单个 Ticker 分析页 ────────────────────────────────────────────────────────
def render_ticker(ticker: str, data: dict) -> None:
    quote = data.get("quote", {})
    gex   = data.get("gex", {})
    dex   = data.get("dex", {})
    setup = data.get("setup", "")

    spot = quote.get("price") or gex.get("spot", 0)

    # ── 顶部信息栏 ──
    col_left, col_right = st.columns([3, 1])
    with col_left:
        change     = quote.get("change", 0)
        change_pct = quote.get("change_pct", 0)
        color = "green" if change >= 0 else "red"
        arrow = "▲" if change >= 0 else "▼"
        st.markdown(
            f"### ${spot:.2f} "
            f"<span style='color:{'#3fb950' if change>=0 else '#f85149'};font-size:18px'>"
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

    if not gex and not quote:
        no_data_placeholder(ticker)
        return

    st.divider()

    # ── 五指标行 ──
    pcr_oi  = gex.get("put_call_oi")
    pcr_vol = gex.get("put_call_vol")
    metric_row(gex, dex, pcr_oi, pcr_vol)

    st.divider()

    # ── 图表 + 层级 ──
    col_chart, col_levels = st.columns([3, 1])
    with col_chart:
        tab_gex, tab_dex = st.tabs(["📊 GEX 分布", "📈 DEX 分布"])
        with tab_gex:
            fig = gex_bar_chart(ticker, gex, spot)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("GEX 逐 strike 数据暂无")
        with tab_dex:
            fig2 = dex_bar_chart(ticker, dex, spot)
            if fig2:
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("DEX 逐 strike 数据暂无")

    with col_levels:
        st.markdown("**关键价格层级**")
        if spot:
            render_levels(spot, gex)
        else:
            st.info("暂无层级数据")

    # ── 机构分析 ──
    if setup:
        with st.expander("🏦 机构行为解读 & 操作建议", expanded=True):
            st.markdown(setup)

    # ── 仓位建议 ──
    call_wall = gex.get("call_wall")
    put_wall  = gex.get("put_wall")
    flip      = gex.get("flip_level")
    if call_wall and put_wall and flip and spot:
        with st.expander("📋 仓位管理快速参考", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**✅ 已持仓（+20%）**")
                t1 = call_wall * 1.03
                t2 = call_wall * 1.06
                st.markdown(f"- 止盈 T1：**${t1:.2f}**（+{(t1-spot)/spot*100:.1f}%）")
                st.markdown(f"- 止盈 T2：**${t2:.2f}**（+{(t2-spot)/spot*100:.1f}%）")
                st.markdown(f"- 止损线：**${flip:.2f}**（Gamma Flip）")
            with c2:
                st.markdown("**💵 候场买入区**")
                buy1_lo = call_wall * 0.97
                buy1_hi = call_wall * 0.99
                buy2_lo = put_wall * 1.00
                buy2_hi = put_wall * 1.02
                st.markdown(f"- 第一买入区：**${buy1_lo:.2f} – ${buy1_hi:.2f}**")
                st.markdown(f"- Put Wall 买入：**${buy2_lo:.2f} – ${buy2_hi:.2f}**")
                st.markdown(f"- 止损参考：**${flip:.2f}**")


# ── 历史趋势 ──────────────────────────────────────────────────────────────────
def render_history() -> None:  # noqa: C901
    rows = load_history()
    if len(rows) < 2:
        st.info("历史数据不足 2 条，待下次运行后累积。每次执行 stock-dashboard-update 自动追加一条快照。", icon="⏳")
        return

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time")
    tickers = sorted(df["ticker"].unique())

    # ── 价格走势 ──
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

    # ── Net GEX 趋势 ──
    st.markdown("#### Net GEX 趋势 (M)")
    fig_gex = go.Figure()
    for t in tickers:
        tdf = df[df["ticker"] == t].dropna(subset=["net_gex"])
        fig_gex.add_trace(go.Bar(
            x=tdf["time"], y=tdf["net_gex"] / 1e6, name=t,
        ))
    fig_gex.update_layout(
        barmode="group",
        plot_bgcolor="#0d1117", paper_bgcolor="#161b22", font_color="#e6edf3",
        xaxis=dict(color="#8b949e", gridcolor="#30363d"),
        yaxis=dict(title="Net GEX (M)", color="#8b949e", gridcolor="#30363d"),
        legend=dict(bgcolor="#161b22", bordercolor="#30363d"),
        margin=dict(l=10, r=10, t=10, b=10), height=260,
    )
    st.plotly_chart(fig_gex, use_container_width=True)

    # ── Regime 历史表 ──
    st.markdown("#### Regime 变化记录")
    REGIME_EMOJI = {"long": "🟢 Long", "short": "🔴 Short", "mixed": "⚠️ Mixed"}
    pivot = (
        df.pivot_table(index="time", columns="ticker", values="regime", aggfunc="last")
          .sort_index(ascending=False)
    )
    pivot.index = pivot.index.strftime("%Y-%m-%d %H:%M")
    pivot = pivot.map(lambda v: REGIME_EMOJI.get(str(v).lower(), v) if pd.notna(v) else "—")
    st.dataframe(pivot, use_container_width=True)


# ── 侧边栏 ───────────────────────────────────────────────────────────────────
def render_sidebar(data: dict) -> str:
    st.sidebar.title("📊 Stock Dashboard")
    st.sidebar.markdown("---")

    generated_at = data.get("generated_at", "")
    expiry       = data.get("expiry", "—")
    if generated_at:
        try:
            ts = datetime.fromisoformat(generated_at)
            st.sidebar.success(f"数据更新：{ts.strftime('%Y-%m-%d %H:%M')}")
        except Exception:
            st.sidebar.info(f"数据时间：{generated_at}")
    else:
        st.sidebar.warning("暂无数据，等待定时任务运行")

    st.sidebar.markdown(f"**到期日：** `{expiry}`")
    st.sidebar.markdown("---")

    tickers = list(data.get("tickers", {}).keys()) or list(TICKER_NAMES.keys())
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
        "定时任务每天自动更新，非实时报价"
    )
    return selected


# ── 主入口 ───────────────────────────────────────────────────────────────────
def main() -> None:
    data = load_data()

    selected = render_sidebar(data)

    tab_now, tab_hist = st.tabs(["📊 当前分析", "📈 历史趋势"])

    with tab_now:
        st.title(f"📊 {selected} · {TICKER_NAMES.get(selected, '')} 期权结构分析")
        st.caption(
            f"GEX / DEX · Dealer Positioning · 到期日 {data.get('expiry', '—')} · "
            "数据由 Stocks Intelligence MCP 采集"
        )

        tickers_data = data.get("tickers", {})
        ticker_data  = tickers_data.get(selected, {})
        render_ticker(selected, ticker_data)

        # 底部横向概览（所有标的）
        if len(tickers_data) > 1:
            st.divider()
            st.subheader("📋 全标的概览")
            cols = st.columns(len(tickers_data))
            for col, (t, td) in zip(cols, tickers_data.items()):
                with col:
                    q    = td.get("quote", {})
                    gex  = td.get("gex",   {})
                    spot = q.get("price") or gex.get("spot", 0)
                    label, fg, bg = regime_label(gex)
                    chg  = q.get("change_pct", 0)
                    st.markdown(
                        f"<div style='background:#161b22;border:1px solid #30363d;"
                        f"border-radius:10px;padding:14px;text-align:center'>"
                        f"<div style='font-size:16px;font-weight:700'>{t}</div>"
                        f"<div style='font-size:22px;font-weight:700;margin:4px 0'>"
                        f"${spot:.2f}</div>"
                        f"<div style='color:{'#3fb950' if chg>=0 else '#f85149'};font-size:13px'>"
                        f"{'▲' if chg>=0 else '▼'} {chg:+.2f}%</div>"
                        f"<div style='margin-top:8px;font-size:11px;background:{bg};"
                        f"color:{fg};border-radius:12px;padding:3px 8px'>{label}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    with tab_hist:
        st.title("📈 历史趋势")
        st.caption("每次运行 stock-dashboard-update 自动追加一条快照，按时间展示价格、GEX 和 Regime 变化")
        render_history()


if __name__ == "__main__":
    main()
