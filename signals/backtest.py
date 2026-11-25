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
SPEC = {"short": [5, 20], "trend": [20, 60]}          # 毎日の検証(直近約2年)
SPEC_LONG = {"trend": [60, 120, 250]}                 # 週1回の長期検証(10年)

BUCKETS = {
    "short": [("0〜29点", 0, 29), ("30〜49点", 30, 49), ("50点以上", 50, 999)],
    "trend": [("30点未満", -1, 29), ("30〜39点", 30, 39), ("40点以上", 40, 999)],
}
PCT_BUCKETS = [("上位10%", 0.9, 1.01), ("上位10〜30%", 0.7, 0.9), ("下位70%", 0.0, 0.7)]


def collect(prices: dict[str, pd.DataFrame], spec: dict, step: int = STEP) -> pd.DataFrame:
    hs = sorted({h for v in spec.values() for h in v})
    need_short, need_trend = "short" in spec, "trend" in spec
    rows = []
    for t, raw in prices.items():
        if len(raw) < START + max(hs) + 5:
            continue
        df = add_indicators(raw)
        close = df["Close"].to_numpy()
        dates = df.index
        n = len(df)
        for i in range(START, n - min(hs), step):
            sub = df.iloc[: i + 1]
            rec = {"date": dates[i], "t": t}
            if need_short:
                rec["short"] = short_score(sub)[0]
            if need_trend:
                rec["trend"] = long_trend_score(sub)[0]
            for h in hs:
                rec[f"r{h}"] = close[i + h] / close[i] - 1 if i + h < n else np.nan
            rows.append(rec)
    return pd.DataFrame(rows)


def _stat(g, col):
    if len(g) < 30:
        return {"n": int(len(g))}
    return {"n": int(len(g)), "win": round(float((g[col] > 0).mean()), 3),
            "mean": round(float(g[col].mean()), 4), "excess": round(float(g["ex"].mean()), 4)}


def summarize(rec: pd.DataFrame, spec: dict) -> dict:
    out = {}
    for kind, hs in spec.items():
        out[kind] = {}
        for h in hs:
            col = f"r{h}"
            d = rec.dropna(subset=[col, kind]).copy()
            if d.empty:
                continue
            d["ex"] = d[col] - d.groupby("date")[col].transform("mean")
            rows = [{"label": label, **_stat(d[(d[kind] >= lo) & (d[kind] <= hi)], col)}
                    for label, lo, hi in BUCKETS[kind]]
            out[kind][f"{h}d"] = {
                "all": {"n": int(len(d)), "win": round(float((d[col] > 0).mean()), 3),
                        "mean": round(float(d[col].mean()), 4)},
                "buckets": rows,
            }
    return out


def run(prices: dict[str, pd.DataFrame]) -> dict:
    """毎日の検証(直近約2年)。"""
    rec = collect(prices, SPEC)
    if rec.empty:
        return {}
    res = summarize(rec, SPEC)
    res["period"] = [str(rec["date"].min().date()), str(rec["date"].max().date())]
    res["tickers"] = int(rec["t"].nunique())
    res["thresholds"] = {"short": CFG["short_threshold"]}
    return res


def run_long(prices: dict[str, pd.DataFrame]) -> dict:
    """週1回の長期検証(10年)。トレンド点を、絶対点数の区切りと「その日の上位N%」の両方で評価し、年別の安定性も出す。"""
    rec = collect(prices, SPEC_LONG, step=5)
    if rec.empty:
        return {}
    res = summarize(rec, SPEC_LONG)
    rec["pct"] = rec.groupby("date")["trend"].rank(pct=True)
    res["pct"], res["by_year"] = {}, {}
    for h in SPEC_LONG["trend"]:
        col = f"r{h}"
        d = rec.dropna(subset=[col]).copy()
        d["ex"] = d[col] - d.groupby("date")[col].transform("mean")
        res["pct"][f"{h}d"] = {"buckets": [{"label": lb, **_stat(d[(d["pct"] >= lo) & (d["pct"] < hi)], col)}
                                           for lb, lo, hi in PCT_BUCKETS]}
        if h == 120:
            top = d[d["trend"] >= 40]
            for y, g in top.groupby(top["date"].dt.year):
                res["by_year"][str(y)] = _stat(g, col)
    res["period"] = [str(rec["date"].min().date()), str(rec["date"].max().date())]
    res["tickers"] = int(rec["t"].nunique())
    return res
