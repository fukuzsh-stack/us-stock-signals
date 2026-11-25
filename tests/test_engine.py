"""模擬データでエンジンを検証: python -m tests.test_engine"""
import json

import numpy as np
import pandas as pd

from signals.indicators import add_indicators, rsi
from signals.main import OUT, build, diff_new_signals, format_message
from signals.scoring import analyst_score, fundamental_score, score_ticker, short_score


def synth(seed, drift, vol=0.015, n=504, shock=None, vol_spike=False):
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, n)
    if shock:  # 直近の急落→反発
        r[-12:-4] = -0.03
        r[-4:] = 0.02
    close = 100 * np.exp(np.cumsum(r))
    v = rng.integers(8e5, 1.2e6, n).astype(float)
    if vol_spike:
        v[-1] = 3e6
    idx = pd.bdate_range(end="2026-11-24", periods=n)
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                         "Close": close, "Volume": v}, index=idx)


def test_rsi_bounds():
    s = pd.Series(np.linspace(1, 100, 100))
    assert rsi(s).iloc[-1] == 100
    s = pd.Series(np.linspace(100, 1, 100))
    assert rsi(s).iloc[-1] < 1


def test_fundamentals():
    good = {"forwardPE": 12, "pegRatio": 0.8, "returnOnEquity": 0.25, "revenueGrowth": 0.15,
            "earningsGrowth": 0.2, "debtToEquity": 30, "profitMargins": 0.2}
    assert fundamental_score(good)[0] == 50
    assert fundamental_score({})[0] is None
    assert fundamental_score({"forwardPE": float("nan")})[0] == 0


def test_analyst():
    f = {"numberOfAnalystOpinions": 30, "recommendationMean": 1.6, "recommendationKey": "strong_buy",
         "targetMeanPrice": 130}
    pts, rs, info = analyst_score(f, 100)
    assert pts == 20 and info["upside"] == 0.3 and rs
    assert analyst_score({"numberOfAnalystOpinions": 3, "recommendationMean": 1.2}, 100)[0] is None
    assert analyst_score({}, 100)[0] is None
    # 項目が欠けても 100点満点に換算される
    df = add_indicators(synth(3, 0.001))
    full = score_ticker(df, {"forwardPE": 10, "returnOnEquity": 0.3, **f})
    assert 0 <= full["long"] <= 100 and full["analyst"]["n_analysts"] == 30
    assert score_ticker(df, None)["analyst"] is None


def test_short_rebound():
    df = add_indicators(synth(1, 0.0008, shock=True, vol_spike=True))
    pts, rs = short_score(df)
    assert pts > 0 and rs


def run_demo():
    rng = np.random.default_rng(0)
    names = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "JPM", "V", "UNH",
             "XOM", "JNJ", "PG", "HD", "COST", "KO", "PEP", "MRK", "ABBV", "CVX",
             "AVGO", "LLY", "WMT", "MA", "BAC", "ORCL", "CRM", "NFLX", "AMD", "INTC"]
    uni = pd.DataFrame({"t": names, "name": [f"Demo {n}" for n in names],
                        "sector": rng.choice(["Information Technology", "Financials", "Health Care",
                                              "Energy", "Consumer Staples"], len(names))})
    prices, funds = {}, {}
    for i, t in enumerate(names + ["VOO", "QQQ"]):
        prices[t] = synth(i, rng.normal(0.0005, 0.0008), shock=(i % 4 == 0), vol_spike=(i % 5 == 0))
        if t not in ("VOO", "QQQ"):
            funds[t] = {"forwardPE": float(rng.uniform(8, 45)), "pegRatio": float(rng.uniform(0.5, 3)),
                        "returnOnEquity": float(rng.uniform(0, 0.4)), "revenueGrowth": float(rng.uniform(-0.1, 0.3)),
                        "earningsGrowth": float(rng.uniform(-0.2, 0.4)), "debtToEquity": float(rng.uniform(10, 200)),
                        "profitMargins": float(rng.uniform(0, 0.3))}
    cur, charts = build(uni, ["VOO", "QQQ", "NVDA"], prices, funds)
    assert len(charts["s"]["AAPL"][0]) == len(charts["dates"]) == 252
    cur["demo"] = True
    json.dumps(cur)  # シリアライズ可能か
    from signals import backtest
    import time
    t0 = time.time()
    bt = backtest.run(prices)
    print("backtest sec", round(time.time() - t0, 1), bt["period"], bt["short"]["20d"]["buckets"])
    json.dumps(bt)
    (OUT / "backtest.json").write_text(json.dumps(bt, ensure_ascii=False, separators=(",", ":")))
    (OUT / "charts.json").write_text(json.dumps(charts, separators=(",", ":")))
    nl, ns = diff_new_signals(None, cur)
    print(format_message(cur, None, nl, ns))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "signals.json").write_text(json.dumps(cur, ensure_ascii=False, separators=(",", ":")))
    print("long sig:", sum(s["long_sig"] for s in cur["stocks"]),
          "short sig:", sum(s["short_sig"] for s in cur["stocks"]))


if __name__ == "__main__":
    test_rsi_bounds(); test_fundamentals(); test_analyst(); test_short_rebound()
    print("unit tests OK")
    run_demo()
