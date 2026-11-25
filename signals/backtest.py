"""過去の株価でシグナルを再現し、点灯後の値動きを集計する(的中率の検証)。

検証できるのは株価だけで決まる部分(短期スコア・長期スコアのトレンド部分)。
財務・アナリスト評価は過去の値が残っていないので対象外。
比較の基準は「同じ日の全銘柄の平均リターン」(これを上回れば市場平均より良かったことになる)。

注意: 現在のS&P500の構成銘柄だけで検証している(過去に除外された銘柄が入らない)ため、
成績はやや良く出る傾向がある。あくまで目安。
"""
import numpy as np
import pandas as pd

from .config import CFG
from .indicators import add_indicators
from .scoring import long_trend_score, short_score

START = 260   # 200日線・1年モメンタムが計算できるまでの助走
STEP = 2      # 2営業日おきに判定(重複を減らし、計算時間も半分に)
HORIZONS = {"short": [5, 20], "trend": [20, 60]}

BUCKETS = {
    "short": [("0〜29点", 0, 29), ("30〜49点", 30, 49), ("50点以上", 50, 999)],
    "trend": [("30点未満", -1, 29), ("30〜39点", 30, 39), ("40点以上", 40, 999)],
}


def collect(prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    maxh = max(max(v) for v in HORIZONS.values())
    for t, raw in prices.items():
        if len(raw) < START + maxh + 5:
            continue
        df = add_indicators(raw)
        close = df["Close"].to_numpy()
        dates = df.index
        n = len(df)
        for i in range(START, n - 5, STEP):
            sub = df.iloc[: i + 1]
            s, _ = short_score(sub)
            tr, _ = long_trend_score(sub)
            rec = {"date": dates[i], "t": t, "short": s, "trend": tr}
            for h in {h for v in HORIZONS.values() for h in v}:
                rec[f"r{h}"] = close[i + h] / close[i] - 1 if i + h < n else np.nan
            rows.append(rec)
    return pd.DataFrame(rows)


def summarize(rec: pd.DataFrame) -> dict:
    out = {}
    for kind, hs in HORIZONS.items():
        out[kind] = {}
        for h in hs:
            col = f"r{h}"
            d = rec.dropna(subset=[col, kind]).copy()
            if d.empty:
                continue
            d["ex"] = d[col] - d.groupby("date")[col].transform("mean")
            rows = []
            for label, lo, hi in BUCKETS[kind]:
                g = d[(d[kind] >= lo) & (d[kind] <= hi)]
                if len(g) < 30:
                    rows.append({"label": label, "n": int(len(g))})
                    continue
                rows.append({
                    "label": label, "n": int(len(g)),
                    "win": round(float((g[col] > 0).mean()), 3),
                    "mean": round(float(g[col].mean()), 4),
                    "excess": round(float(g["ex"].mean()), 4),
                })
            out[kind][f"{h}d"] = {
                "all": {"n": int(len(d)), "win": round(float((d[col] > 0).mean()), 3),
                        "mean": round(float(d[col].mean()), 4)},
                "buckets": rows,
            }
    return out


def run(prices: dict[str, pd.DataFrame]) -> dict:
    rec = collect(prices)
    if rec.empty:
        return {}
    res = summarize(rec)
    res["period"] = [str(rec["date"].min().date()), str(rec["date"].max().date())]
    res["tickers"] = int(rec["t"].nunique())
    res["thresholds"] = {"short": CFG["short_threshold"]}
    return res
