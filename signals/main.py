"""毎日の実行入口: python -m signals.main"""
import json
import os

import pandas as pd

from . import backtest, data, notify
from .config import CFG
from .indicators import add_indicators
from .scoring import score_ticker

OUT = data.ROOT / "docs" / "data"
CHART_DAYS = 252


def build(universe: pd.DataFrame, watch: list[str], prices: dict, funds: dict):
    """戻り値: (signals.json の中身, チャート用データ)"""
    meta = {r.t: (r.name, r.sector) for r in universe.itertuples()}
    stocks, inds = [], {}
    last_date = None
    for t, df in prices.items():
        df = add_indicators(df)
        inds[t] = df
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
    cur = {
        "generated_at": data.utc_now_iso(),
        "market_date": str(pd.Timestamp(last_date).date()) if last_date is not None else None,
        "thresholds": {"long": CFG["long_threshold"], "short": CFG["short_threshold"]},
        "count": len(stocks),
        "stocks": stocks,
    }
    return cur, build_charts(inds)


def build_charts(inds: dict) -> dict:
    """個別銘柄の詳細画面用: 直近1年の終値・50日線・200日線(共通の日付軸にそろえる)。"""
    if not inds:
        return {}
    base = max(inds.values(), key=len).index[-CHART_DAYS:]

    def arr(series):
        s = series.reindex(base).ffill()
        return [None if pd.isna(x) else round(float(x), 2) for x in s]

    return {
        "dates": [str(pd.Timestamp(d).date()) for d in base],
        "s": {t: [arr(df["Close"]), arr(df["sma50"]), arr(df["sma200"])] for t, df in inds.items()},
    }


def diff_new_signals(prev: dict | None, cur: dict):
    old_l = {s["t"] for s in (prev or {}).get("stocks", []) if s.get("long_sig")}
    old_s = {s["t"] for s in (prev or {}).get("stocks", []) if s.get("short_sig")}
    new_l = [s for s in cur["stocks"] if s["long_sig"] and s["t"] not in old_l]
    new_s = [s for s in cur["stocks"] if s["short_sig"] and s["t"] not in old_s]
    new_l.sort(key=lambda s: -s["long"])
    new_s.sort(key=lambda s: -s["short"])
    return new_l, new_s


def format_message(cur, prev, new_l, new_s) -> str | None:
    """通知は「重要なものだけ」。何も無ければ None(送らない)。
    1) ウォッチリスト銘柄: 新しく点灯したもの、注意サインが出ているもの
    2) 新しく点灯した長期候補・短期シグナルの上位だけ(件数は config の notify_top_n)
    """
    n = CFG["notify_top_n"]
    old = {s["t"]: s for s in (prev or {}).get("stocks", [])}
    lines = []

    watch_lines = []
    for s in cur["stocks"]:
        if not s["watch"]:
            continue
        o = old.get(s["t"], {})
        bits = []
        if s["long_sig"] and not o.get("long_sig"):
            bits.append(f"長期{s['long']}点で点灯")
        if s["short_sig"] and not o.get("short_sig"):
            bits.append(f"短期{s['short']}点で点灯")
        new_warns = [w for w in s.get("warns", []) if w not in o.get("warns", [])]
        if new_warns:
            bits.append("注意: " + "/".join(new_warns))
        if bits:
            watch_lines.append(f"★{s['t']} " + "、".join(bits))
    if watch_lines:
        lines.append("■ウォッチリスト")
        lines += watch_lines

    def top(title, items, key):
        if not items:
            return
        lines.append(f"■{title}(新規{len(items)}件のうち上位)")
        for s in items[:n]:
            lines.append(f"{s['t']} {s[key]}点 ${s['price']}")

    top("長期候補", new_l, "long")
    top("短期シグナル", new_s, "short")
    if not lines:
        return None
    return f"{cur['market_date']} 終値ベース\n" + "\n".join(lines)


def run():
    universe = data.load_sp500()
    watch = data.load_watchlist()
    tickers = sorted(set(universe["t"]) | set(watch))
    print(f"tickers: {len(tickers)}")
    prices = data.download_prices(tickers, CFG["history_period"])
    print(f"prices ok: {len(prices)}")
    funds = data.load_fundamentals(tickers, CFG["fundamental_refresh_days"])
    cur, charts = build(universe, watch, prices, funds)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "signals.json"
    prev = json.loads(path.read_text()) if path.exists() else None
    if prev and prev.get("market_date") == cur["market_date"]:
        prev_path = OUT / "signals_prev.json"
        prev = json.loads(prev_path.read_text()) if prev_path.exists() else None
    elif prev:
        (OUT / "signals_prev.json").write_text(json.dumps(prev, ensure_ascii=False))
    path.write_text(json.dumps(cur, ensure_ascii=False, separators=(",", ":")))
    # チャートは容量が大きいのでGitには保存せず、公開ページにだけ載せる(.gitignore済み)
    (OUT / "charts.json").write_text(json.dumps(charts, separators=(",", ":")))

    # シグナル履歴
    hist_path = OUT / "history.json"
    hist = json.loads(hist_path.read_text()) if hist_path.exists() else []
    hist = [h for h in hist if h["date"] != cur["market_date"]]
    hist.append({
        "date": cur["market_date"],
        "long": [[s["t"], s["long"], s["price"]] for s in cur["stocks"] if s["long_sig"]],
        "short": [[s["t"], s["short"], s["price"]] for s in cur["stocks"] if s["short_sig"]],
    })
    hist_path.write_text(json.dumps(hist[-400:], ensure_ascii=False, separators=(",", ":")))

    # 過去の的中率の検証(失敗しても本体の処理は止めない)
    try:
        bt = backtest.run(prices)
        (OUT / "backtest.json").write_text(json.dumps(bt, ensure_ascii=False, separators=(",", ":")))
        print("backtest period:", bt.get("period"))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] backtest failed: {e}")

    new_l, new_s = diff_new_signals(prev, cur)
    msg = format_message(cur, prev, new_l, new_s)
    print(msg or "(通知する内容なし)")
    # 通知は自動実行(NOTIFY_ENABLED=true)のときだけ。手動実行で何度も鳴らさない
    if msg and (os.environ.get("NOTIFY_ENABLED") == "true" or os.environ.get("NOTIFY_ALWAYS")):
        notify.send("米国株シグナル", msg, os.environ.get("PAGE_URL"))


if __name__ == "__main__":
    run()
