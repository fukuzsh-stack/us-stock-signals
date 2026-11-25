"""毎日の実行入口: python -m signals.main"""
import json
import os

import pandas as pd

from . import data, notify
from .config import CFG
from .indicators import add_indicators
from .scoring import score_ticker

OUT = data.ROOT / "docs" / "data"


def build(universe: pd.DataFrame, watch: list[str], prices: dict, funds: dict) -> dict:
    meta = {r.t: (r.name, r.sector) for r in universe.itertuples()}
    stocks = []
    last_date = None
    for t, df in prices.items():
        df = add_indicators(df)
        s = score_ticker(df, funds.get(t))
        f = funds.get(t) or {}
        name, sector = meta.get(t, (f.get("shortName") or t, f.get("sector") or "-"))
        d = df.index[-1]
        last_date = max(last_date, d) if last_date is not None else d
        stocks.append({
            "t": t, "name": name, "sector": sector,
            "sp500": t in meta, "watch": t in watch, **s,
            "long_sig": s["long"] is not None and s["long"] >= CFG["long_threshold"],
            "short_sig": s["short"] >= CFG["short_threshold"],
        })
    return {
        "generated_at": data.utc_now_iso(),
        "market_date": str(pd.Timestamp(last_date).date()) if last_date is not None else None,
        "thresholds": {"long": CFG["long_threshold"], "short": CFG["short_threshold"]},
        "count": len(stocks),
        "stocks": stocks,
    }


def diff_new_signals(prev: dict | None, cur: dict):
    old_l = {s["t"] for s in (prev or {}).get("stocks", []) if s.get("long_sig")}
    old_s = {s["t"] for s in (prev or {}).get("stocks", []) if s.get("short_sig")}
    new_l = [s for s in cur["stocks"] if s["long_sig"] and s["t"] not in old_l]
    new_s = [s for s in cur["stocks"] if s["short_sig"] and s["t"] not in old_s]
    new_l.sort(key=lambda s: -s["long"])
    new_s.sort(key=lambda s: -s["short"])
    return new_l, new_s


def format_message(cur, new_l, new_s) -> str:
    def line(s, key):
        star = "★" if s["watch"] else ""
        return f"{star}{s['t']} {s[key]}点 ${s['price']}"

    watch_hits = [s for s in cur["stocks"] if s["watch"] and (s["long_sig"] or s["short_sig"])]
    parts = [f"{cur['market_date']} 終値ベース"]
    parts.append(f"■新しい長期候補 {len(new_l)}件")
    parts += [line(s, "long") for s in new_l[:5]]
    parts.append(f"■新しい短期シグナル {len(new_s)}件")
    parts += [line(s, "short") for s in new_s[:5]]
    if watch_hits:
        parts.append("■ウォッチリストで点灯中: " + ", ".join(s["t"] for s in watch_hits))
    return "\n".join(parts)


def run():
    universe = data.load_sp500()
    watch = data.load_watchlist()
    tickers = sorted(set(universe["t"]) | set(watch))
    print(f"tickers: {len(tickers)}")
    prices = data.download_prices(tickers, CFG["history_period"])
    print(f"prices ok: {len(prices)}")
    funds = data.load_fundamentals(tickers, CFG["fundamental_refresh_days"])
    cur = build(universe, watch, prices, funds)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "signals.json"
    prev = json.loads(path.read_text()) if path.exists() else None
    if prev and prev.get("market_date") == cur["market_date"]:
        prev_path = OUT / "signals_prev.json"
        prev = json.loads(prev_path.read_text()) if prev_path.exists() else None
    elif prev:
        (OUT / "signals_prev.json").write_text(json.dumps(prev, ensure_ascii=False))
    path.write_text(json.dumps(cur, ensure_ascii=False, separators=(",", ":")))

    # シグナル履歴(後で「当たっていたか」を検証するため)
    hist_path = OUT / "history.json"
    hist = json.loads(hist_path.read_text()) if hist_path.exists() else []
    hist = [h for h in hist if h["date"] != cur["market_date"]]
    hist.append({
        "date": cur["market_date"],
        "long": [[s["t"], s["long"], s["price"]] for s in cur["stocks"] if s["long_sig"]],
        "short": [[s["t"], s["short"], s["price"]] for s in cur["stocks"] if s["short_sig"]],
    })
    hist_path.write_text(json.dumps(hist[-400:], ensure_ascii=False, separators=(",", ":")))

    new_l, new_s = diff_new_signals(prev, cur)
    msg = format_message(cur, new_l, new_s)
    print(msg)
    if new_l or new_s or os.environ.get("NOTIFY_ALWAYS"):
        notify.send("米国株シグナル", msg, os.environ.get("PAGE_URL"))


if __name__ == "__main__":
    run()
