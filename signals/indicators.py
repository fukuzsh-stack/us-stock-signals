"""テクニカル指標の計算(pandas のみで実装)。"""
import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(100)


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger(close: pd.Series, n=20, k=2.0):
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std()
    return mid - k * sd, mid, mid + k * sd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """df: columns Open, High, Low, Close, Volume (日足)"""
    df = df.copy()
    c = df["Close"]
    df["sma50"] = sma(c, 50)
    df["sma200"] = sma(c, 200)
    df["rsi"] = rsi(c)
    df["macd"], df["macd_sig"], df["macd_hist"] = macd(c)
    df["bb_lo"], df["bb_mid"], df["bb_hi"] = bollinger(c)
    df["vol20"] = df["Volume"].rolling(20, min_periods=20).mean()
    df["high252"] = c.rolling(252, min_periods=120).max()
    return df
