# market_data.py
import yfinance as yf
import pandas as pd
from app.models import StockMetrics


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def calculate_atr(hist: pd.DataFrame, period: int = 14) -> float:
    if hist.empty or len(hist) < period + 1:
        return 0.0

    high = hist["High"]
    low = hist["Low"]
    close = hist["Close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1
    ).max(axis=1)

    atr = tr.rolling(period).mean().iloc[-1]
    return float(atr) if pd.notna(atr) else 0.0


def get_stock_metrics(symbol: str):
    try:
        hist = yf.download(
            symbol,
            period="3mo",
            progress=False,
            auto_adjust=False,
            multi_level_index=False,
        )

        if hist is None or hist.empty or len(hist) < 30:
            print(f"[WARN] No/insufficient history for {symbol}")
            return None

        hist = normalize_columns(hist)

        required_cols = {"Close", "Volume", "High", "Low"}
        if not required_cols.issubset(set(hist.columns)):
            print(f"[WARN] Missing required columns for {symbol}: {hist.columns.tolist()}")
            return None

        close = hist["Close"]
        volume = hist["Volume"]

        price = float(close.iloc[-1])
        price_1m_ago = float(close.iloc[-22]) if len(close) > 22 else float(close.iloc[0])
        momentum_1m = (price - price_1m_ago) / price_1m_ago if price_1m_ago else 0.0

        avg_volume = float(volume.tail(20).mean()) if len(volume) >= 20 else float(volume.mean())
        current_volume = float(volume.iloc[-1])
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = float((macd - macd_signal).iloc[-1])

        atr = calculate_atr(hist)

        score = (
            min(max(momentum_1m, -0.2), 0.2) * 100 * 0.35 +
            min(volume_ratio, 3.0) * 15 +
            max(macd_hist, 0) * 8
        )

        return StockMetrics(
            symbol=symbol,
            price=price,
            momentum_1m=momentum_1m,
            volume_ratio=volume_ratio,
            macd_hist=macd_hist,
            atr=atr,
            score=round(score, 2),
        )

    except Exception as e:
        print(f"[ERROR] get_stock_metrics failed for {symbol}: {e}")
        return None
