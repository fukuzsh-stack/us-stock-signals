"""データ取得: 対象銘柄リスト、株価(日足)、財務データ。すべて yfinance / Wikipedia(無料)。"""
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
UA = {"User-Agent": "Mozilla/5.0 (us-stock-signals)"}


def yf_symbol(t: str) -> str:
    return t.strip().upper().replace(".", "-")


def load_watchlist() -> list[str]:
    p = ROOT / "watchlist.txt"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            out.append(yf_symbol(line))
    return out


def load_sp500() -> pd.DataFrame:
    """Wikipedia から S&P500 構成銘柄を取得。失敗時は前回のキャッシュ。"""
    cache = CACHE / "sp500.csv"
    try:
        html = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=UA, timeout=30
        ).text
        df = pd.read_html(io.StringIO(html))[0]
        df = df.rename(columns={"Symbol": "t", "Security": "name", "GICS Sector": "sector"})[
            ["t", "name", "sector"]
        ]
        df["t"] = df["t"].map(yf_symbol)
        CACHE.mkdir(exist_ok=True)
        df.to_csv(cache, index=False)
        return df
    except Exception as e:  # noqa: BLE001
        print(f"[warn] S&P500 list fetch failed: {e}; using cache")
        return pd.read_csv(cache)


def download_prices(tickers: list[str], period: str) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    out = {}
    for i in range(0, len(tickers), 100):
        chunk = tickers[i : i + 100]
        raw = yf.download(
            chunk, period=period, interval="1d", group_by="ticker",
            auto_adjust=True, threads=True, progress=False,
        )
        for t in chunk:
            try:
                df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                df = df.dropna(subset=["Close"])
                if len(df) >= 60:
                    out[t] = df
            except KeyError:
                pass
        time.sleep(1)
    return out


FUND_KEYS = [
    "forwardPE", "trailingPE", "pegRatio", "trailingPegRatio", "returnOnEquity",
    "revenueGrowth", "earningsGrowth", "debtToEquity", "profitMargins",
    "shortName", "sector",
]


def load_fundamentals(tickers: list[str], refresh_days: int, max_per_run: int = 200) -> dict:
    """財務データをキャッシュ付きで取得。古い順に max_per_run 件だけ更新(レート制限対策)。"""
    import yfinance as yf

    path = CACHE / "fundamentals.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    now = time.time()
    stale = [t for t in tickers if now - cache.get(t, {}).get("_ts", 0) > refresh_days * 86400]
    stale.sort(key=lambda t: cache.get(t, {}).get("_ts", 0))
    for t in stale[:max_per_run]:
        try:
            info = yf.Ticker(t).info or {}
            cache[t] = {k: info.get(k) for k in FUND_KEYS} | {"_ts": now}
        except Exception as e:  # noqa: BLE001
            print(f"[warn] fundamentals {t}: {e}")
        time.sleep(0.3)
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps(cache))
    return cache


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
