"""長期・短期スコアの計算。点数と「理由」を日本語で返す。

長期スコア(100点) = 長期トレンド(50) + 割安度・財務(50)
短期スコア(100点) = RSI(25) + MACD(20) + ボリンジャー(20) + 出来高(20) + 上昇トレンド中か(15)
しきい値・配点は config.py で調整できる。
"""
import math

import pandas as pd

from .config import CFG


def _ok(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def long_trend_score(df: pd.DataFrame):
    last = df.iloc[-1]
    pts, reasons = 0, []
    c, s50, s200 = last["Close"], last["sma50"], last["sma200"]
    if not _ok(s200):
        return None, ["データ期間が短く長期トレンド判定不可"]
    if c > s200:
        pts += 12
        reasons.append("株価が200日線より上(長期上昇トレンド)")
    if _ok(s50) and s50 > s200:
        pts += 10
        reasons.append("50日線が200日線より上")
    s200_prev = df["sma200"].iloc[-21] if len(df) > 221 else float("nan")
    if _ok(s200_prev) and s200 > s200_prev:
        pts += 8
        reasons.append("200日線が上向き")
    if len(df) > 252:
        mom = df["Close"].iloc[-22] / df["Close"].iloc[-253] - 1
        if mom > 0.15:
            pts += 10
            reasons.append(f"過去1年の上昇率 {mom:+.0%}(強いモメンタム)")
        elif mom > 0:
            pts += 5
            reasons.append(f"過去1年の上昇率 {mom:+.0%}")
    hi = last["high252"]
    if _ok(hi) and hi > 0:
        dd = 1 - c / hi
        if c > s200 and 0.05 <= dd <= 0.25:
            pts += 10
            reasons.append(f"上昇トレンド中の押し目(高値から -{dd:.0%})")
        elif dd < 0.05:
            pts += 5
            reasons.append("52週高値圏")
    return pts, reasons


def fundamental_score(f: dict):
    if not f:
        return None, ["財務データなし"]
    pts, reasons = 0, []
    pe = f.get("forwardPE") or f.get("trailingPE")
    if _ok(pe) and pe > 0:
        if pe < 15:
            pts += 10; reasons.append(f"PER {pe:.1f}倍(割安)")
        elif pe < 25:
            pts += 7; reasons.append(f"PER {pe:.1f}倍(妥当)")
        elif pe < 35:
            pts += 3
    peg = f.get("pegRatio") or f.get("trailingPegRatio")
    if _ok(peg) and peg > 0:
        if peg < 1:
            pts += 8; reasons.append(f"PEG {peg:.2f}(成長の割に割安)")
        elif peg < 2:
            pts += 4
    roe = f.get("returnOnEquity")
    if _ok(roe):
        if roe > 0.20:
            pts += 8; reasons.append(f"ROE {roe:.0%}(高収益)")
        elif roe > 0.12:
            pts += 5
    rg = f.get("revenueGrowth")
    if _ok(rg):
        if rg > 0.10:
            pts += 8; reasons.append(f"売上成長 {rg:+.0%}")
        elif rg > 0:
            pts += 4
    eg = f.get("earningsGrowth")
    if _ok(eg):
        if eg > 0.10:
            pts += 6; reasons.append(f"利益成長 {eg:+.0%}")
        elif eg > 0:
            pts += 3
    de = f.get("debtToEquity")  # Yahoo は % 表記
    if _ok(de):
        if de < 50:
            pts += 5; reasons.append("負債が少ない")
        elif de < 100:
            pts += 3
    pm = f.get("profitMargins")
    if _ok(pm):
        if pm > 0.15:
            pts += 5; reasons.append(f"利益率 {pm:.0%}")
        elif pm > 0.05:
            pts += 2
    return pts, reasons


def analyst_score(f: dict, price: float):
    """アナリスト評価(20点満点)。推奨平均(1=強い買い〜5=売り)10点 + 目標株価までの上昇余地10点。
    アナリストが5人未満の銘柄は信頼性が低いので評価しない。"""
    n = f.get("numberOfAnalystOpinions") if f else None
    if not _ok(n) or n < 5:
        return None, [], {}
    pts, reasons = 0, []
    rec = f.get("recommendationMean")
    if _ok(rec):
        label = {"strong_buy": "強い買い", "buy": "買い", "hold": "中立", "underperform": "弱気",
                 "sell": "売り"}.get(f.get("recommendationKey"), "")
        if rec <= 1.8:
            pts += 10; reasons.append(f"アナリスト評価 {rec:.1f}/5・{label}(強気・{int(n)}人)")
        elif rec <= 2.3:
            pts += 7; reasons.append(f"アナリスト評価 {rec:.1f}/5・{label}({int(n)}人)")
        elif rec <= 2.8:
            pts += 3
    tgt = f.get("targetMeanPrice")
    upside = None
    if _ok(tgt) and price > 0:
        upside = tgt / price - 1
        if upside > 0.25:
            pts += 10; reasons.append(f"目標株価 ${tgt:.0f}(上昇余地 {upside:+.0%})")
        elif upside > 0.15:
            pts += 7; reasons.append(f"目標株価 ${tgt:.0f}(上昇余地 {upside:+.0%})")
        elif upside > 0.05:
            pts += 3
        elif upside < 0:
            reasons.append(f"株価が目標株価 ${tgt:.0f} を上回っている({upside:+.0%})")
    info = {
        "rec": round(float(rec), 2) if _ok(rec) else None,
        "rec_key": f.get("recommendationKey"),
        "n_analysts": int(n),
        "target": round(float(tgt), 2) if _ok(tgt) else None,
        "upside": round(float(upside), 3) if upside is not None else None,
    }
    return pts, reasons, info


def short_score(df: pd.DataFrame):
    if len(df) < 60:
        return 0, []
    last, prev = df.iloc[-1], df.iloc[-2]
    w = df.iloc[-6:]  # 直近5営業日+今日
    pts, reasons = 0, []

    r = last["rsi"]
    if (w["rsi"].iloc[:-1] < 30).any() and r > prev["rsi"] and r >= 30:
        pts += 25; reasons.append(f"RSIが売られすぎ(30未満)から反発 → {r:.0f}")
    elif r < 30:
        pts += 15; reasons.append(f"RSI {r:.0f}(売られすぎ)")
    elif r < 40 and r > prev["rsi"]:
        pts += 8; reasons.append(f"RSI {r:.0f}で上向き")

    h = df["macd_hist"]
    crossed = any(h.iloc[-i] > 0 and h.iloc[-i - 1] <= 0 for i in range(1, 4))
    if crossed:
        pts += 20; reasons.append("MACDゴールデンクロス(直近3日)")
    elif h.iloc[-1] < 0 and h.iloc[-1] > h.iloc[-2] > h.iloc[-3] > h.iloc[-4]:
        pts += 8; reasons.append("MACDが好転中(クロス目前)")

    below = (w["Close"].iloc[:-1] < w["bb_lo"].iloc[:-1]).any()
    if below and last["Close"] > last["bb_lo"]:
        pts += 20; reasons.append("ボリンジャー下限割れから回復")
    elif last["Close"] < last["bb_lo"]:
        pts += 10; reasons.append("ボリンジャー下限を下回る(行き過ぎ)")

    v20 = last["vol20"]
    up = last["Close"] > prev["Close"]
    if _ok(v20) and v20 > 0 and up:
        ratio = last["Volume"] / v20
        if ratio >= 2:
            pts += 20; reasons.append(f"出来高急増 {ratio:.1f}倍で上昇")
        elif ratio >= 1.5:
            pts += 10; reasons.append(f"出来高増 {ratio:.1f}倍で上昇")

    if _ok(last["sma200"]) and last["Close"] > last["sma200"]:
        pts += 15; reasons.append("200日線より上(下落トレンドではない)")
    return pts, reasons


def caution_signals(df: pd.DataFrame) -> list[str]:
    """保有中・ウォッチ中の銘柄に出す「注意サイン」(売り推奨ではなく、状況が変わった合図)。"""
    if len(df) < 60:
        return []
    last = df.iloc[-1]
    out = []
    s50, s200, c = last["sma50"], last["sma200"], last["Close"]
    if _ok(s200):
        recent = df.iloc[-6:-1]
        if c < s200 and (recent["Close"] >= recent["sma200"]).any():
            out.append("200日線を割り込んだ")
        elif c < s200:
            out.append("200日線より下(長期下降トレンド)")
    if _ok(s50) and _ok(s200) and len(df) > 12:
        d = df["sma50"] - df["sma200"]
        if d.iloc[-1] < 0 and (d.iloc[-11:-1] >= 0).any():
            out.append("デッドクロス(50日線が200日線を下回った)")
    if last["rsi"] >= 75:
        out.append(f"RSI {last['rsi']:.0f}(買われすぎ・過熱)")
    h = df["macd_hist"]
    if any(h.iloc[-i] < 0 and h.iloc[-i - 1] >= 0 for i in range(1, 4)):
        out.append("MACDデッドクロス(直近3日)")
    hi = last["high252"]
    if _ok(hi) and hi > 0 and 1 - c / hi >= 0.25:
        out.append(f"高値から {c / hi - 1:.0%} 下落")
    return out


def score_ticker(df: pd.DataFrame, fund: dict | None):
    t_pts, t_rs = long_trend_score(df)
    f_pts, f_rs = fundamental_score(fund or {})
    price = float(df.iloc[-1]["Close"])
    a_pts, a_rs, a_info = analyst_score(fund or {}, price)
    # 取得できた項目だけで満点を計算し、100点に換算(トレンド50・財務50・アナリスト20)
    parts = [(t_pts, 50), (f_pts, 50), (a_pts, 20)]
    earned = sum(p for p, _ in parts if p is not None)
    avail = sum(m for p, m in parts if p is not None)
    if avail == 0:
        long_pts = None
    else:
        long_pts = round(earned / avail * 100 * (1 if f_pts is not None else CFG["no_fundamental_penalty"]))
    s_pts, s_rs = short_score(df)
    last = df.iloc[-1]
    chg = last["Close"] / df["Close"].iloc[-2] - 1 if len(df) > 1 else 0.0
    return {
        "long": long_pts,
        "long_trend": t_pts,
        "long_fund": f_pts,
        "long_reasons": t_rs + f_rs + a_rs,
        "long_analyst": a_pts,
        "warns": caution_signals(df),
        "sma50": round(float(last["sma50"]), 2) if _ok(last["sma50"]) else None,
        "sma200": round(float(last["sma200"]), 2) if _ok(last["sma200"]) else None,
        "analyst": a_info or None,
        "short": s_pts,
        "short_reasons": s_rs,
        "price": round(float(last["Close"]), 2),
        "change": round(float(chg), 4),
        "rsi": round(float(last["rsi"]), 1),
        "spark": [round(float(x), 2) for x in df["Close"].iloc[-60:]],
    }
