#!/usr/bin/env python3
"""
collect.py — 数据持久化与 GitHub 推送

职责：
  1. 接收标准化股票分析 JSON（由 Claude 生成）
  2. 写入 data/latest.json
  3. 同步写入 data/history/<YYYY-MM-DD_HH-MM>.json
  4. Git commit + push 到 GitHub

用法：
  python collect.py <json_file>   # 从文件读取 payload
  python collect.py               # 从 stdin 读取 payload

环境变量（.env 配置）：
  GITHUB_TOKEN   Personal Access Token
  GITHUB_REPO    username/repo 格式
  GIT_BRANCH     推送分支（默认 main）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data"
HIST_DIR = DATA_DIR / "history"
OUT_FILE = DATA_DIR / "latest.json"


# ── 环境变量 ──────────────────────────────────────────────────────────────────
def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


# ── 文件写入 ──────────────────────────────────────────────────────────────────
def write_snapshot(payload: dict) -> str:
    """写入 latest.json 和历史快照，返回快照文件名。"""
    DATA_DIR.mkdir(exist_ok=True)
    HIST_DIR.mkdir(exist_ok=True)

    if "generated_at" not in payload:
        payload["generated_at"] = datetime.now(timezone.utc).isoformat()

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    try:
        dt = datetime.fromisoformat(payload["generated_at"])
        fname = dt.strftime("%Y-%m-%d_%H-%M") + ".json"
    except Exception:
        fname = datetime.now().strftime("%Y-%m-%d_%H-%M") + ".json"

    with open(HIST_DIR / fname, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"✅ 写入: {OUT_FILE.name}  +  history/{fname}")
    return fname


# ── Git 推送 ──────────────────────────────────────────────────────────────────
def git_push(commit_msg: str) -> bool:
    """Git pull → add → commit → push，返回是否成功。"""
    token  = os.environ.get("GITHUB_TOKEN", "")
    repo   = os.environ.get("GITHUB_REPO", "")
    branch = os.environ.get("GIT_BRANCH", "main")

    if not token or not repo:
        print("⚠️  GITHUB_TOKEN / GITHUB_REPO 未配置，跳过推送")
        return False

    remote = f"https://x-access-token:{token}@github.com/{repo}.git"
    steps = [
        ["git", "config", "user.email", "bot@stockdashboard.local"],
        ["git", "config", "user.name",  "StockBot"],
        ["git", "remote", "set-url", "origin", remote],
        ["git", "pull",   "--rebase",   "origin", branch],
        ["git", "add",    "data/"],
        ["git", "commit", "-m", commit_msg],
        ["git", "push",   "origin", branch],
    ]
    for cmd in steps:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        if r.returncode != 0:
            out = r.stdout + r.stderr
            if any(x in out for x in ["nothing to commit", "rebase"]):
                continue
            print(f"⚠️  git {cmd[1]}: {r.stderr.strip()}")
            return False

    print("✅ 已推送 GitHub → Streamlit 将在 1 分钟内刷新")
    return True


# ── commit 消息 ───────────────────────────────────────────────────────────────
def build_commit_msg(payload: dict) -> str:
    ts = payload.get("generated_at", "")[:16].replace("T", " ")
    emoji = {"long": "🟢", "short": "🔴", "mixed": "⚠️"}
    parts = []
    for ticker, td in payload.get("tickers", {}).items():
        price  = td.get("quote", {}).get("price") or td.get("gex", {}).get("spot", 0)
        regime = td.get("gex", {}).get("regime", "mixed")
        parts.append(f"{ticker} ${price} {emoji.get(regime, '⚪')}{regime.capitalize()}")
    return f"data: {ts} | {' | '.join(parts)}"


# ── 入口 ──────────────────────────────────────────────────────────────────────
def main() -> None:
    load_env()
    if len(sys.argv) > 1:
        payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    else:
        payload = json.load(sys.stdin)

    write_snapshot(payload)
    git_push(build_commit_msg(payload))


if __name__ == "__main__":
    main()
