#!/usr/bin/env python3
"""
定时任务脚本：通过 Claude Code MCP (Stocks Intelligence) 采集分析数据，
输出到 data/latest.json，供 Streamlit Dashboard 读取展示。

由 Claude Code Cron 每天自动调用，不需要手动运行。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import datetime as dt
from pathlib import Path

# ── 配置 ─────────────────────────────────────────────────────────────────────
TICKERS   = ["KO", "QQQ", "SPY"]
EXPIRY    = "2026-09-18"          # 下次大型到期日，每季度更新一次
DATA_DIR  = Path(__file__).parent / "data"
OUT_FILE  = DATA_DIR / "latest.json"
REPO_DIR  = Path(__file__).parent

# GitHub 推送配置（由环境变量读取，Streamlit Secrets 或 .env 中设置）
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "")   # 格式: username/repo-name
GIT_BRANCH   = os.environ.get("GIT_BRANCH", "main")


def git_push(message: str) -> bool:
    """提交并推送 data/latest.json 到 GitHub。"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("⚠️  GITHUB_TOKEN / GITHUB_REPO 未配置，跳过 git push")
        return False
    try:
        remote_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
        cmds = [
            ["git", "-C", str(REPO_DIR), "config", "user.email", "bot@stockdashboard.local"],
            ["git", "-C", str(REPO_DIR), "config", "user.name",  "StockBot"],
            ["git", "-C", str(REPO_DIR), "remote", "set-url", "origin", remote_url],
            ["git", "-C", str(REPO_DIR), "add",    "data/latest.json"],
            ["git", "-C", str(REPO_DIR), "commit", "-m", message],
            ["git", "-C", str(REPO_DIR), "push",   "origin", GIT_BRANCH],
        ]
        for cmd in cmds:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0 and "nothing to commit" not in result.stdout:
                print(f"git 命令失败: {' '.join(cmd)}\n{result.stderr}")
                return False
        print("✅ 数据已推送到 GitHub")
        return True
    except Exception as e:
        print(f"git push 异常: {e}")
        return False


# ── 数据结构模板 ──────────────────────────────────────────────────────────────
def empty_ticker() -> dict:
    return {
        "quote":  {},
        "gex":    {},
        "dex":    {},
        "setup":  "",
        "error":  "",
    }


def build_payload(quotes: dict, gex_map: dict, dex_map: dict, setups: dict) -> dict:
    """把 MCP 各工具返回的原始数据整合成统一 JSON 结构。"""
    tickers_out = {}
    for t in TICKERS:
        tickers_out[t] = {
            "quote":  quotes.get(t, {}),
            "gex":    gex_map.get(t, {}),
            "dex":    dex_map.get(t, {}),
            "setup":  setups.get(t, ""),
        }
    return {
        "generated_at": dt.datetime.now().isoformat(),
        "expiry": EXPIRY,
        "tickers": tickers_out,
    }


# ── 主流程（由 Claude Cron Agent 内部调用） ────────────────────────────────────
def main(quotes: dict, gex_map: dict, dex_map: dict, setups: dict) -> None:
    """
    参数由 Claude Cron Agent 在调用 MCP 工具后直接传入。
    每个参数均为 dict，key 为 ticker 代码。

    quotes  : {ticker: {price, change, change_pct, volume, ...}}
    gex_map : {ticker: {net_gex, flip_level, call_wall, put_wall, regime, strikes: [...]}}
    dex_map : {ticker: {net_dex, top_positive, top_negative, strikes: [...]}}
    setups  : {ticker: "分析文本字符串"}
    """
    DATA_DIR.mkdir(exist_ok=True)
    payload = build_payload(quotes, gex_map, dex_map, setups)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"✅ 数据已写入 {OUT_FILE}")

    ts = dt.date.today().isoformat()
    git_push(f"data: 每日分析更新 {ts}")


if __name__ == "__main__":
    # 直接运行时，生成一个空的样本文件（方便测试 Streamlit 布局）
    DATA_DIR.mkdir(exist_ok=True)
    sample = build_payload({}, {}, {}, {})
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    print(f"样本文件已写入 {OUT_FILE}")
