import pandas as pd
import pandas_ta as ta

class Strategy:
    def __init__(self):
        # Trend Following Setup
        self.ema_short_len = 50
        self.ema_long_len = 200
        self.adx_len = 14
        self.adx_threshold = 20
        self.atr_len = 14

    def parse_data(self, ohlcv):
        """Convert CCXT ohlcv to Pandas DataFrame."""
        if not ohlcv or len(ohlcv) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def calculate_indicators(self, df):
        """Calculate EMAs, ADX and ATR."""
        if df.empty or len(df) < self.ema_long_len:
            return df

        # EMAs
        df['ema_50'] = ta.ema(df['close'], length=self.ema_short_len)
        df['ema_200'] = ta.ema(df['close'], length=self.ema_long_len)

        # ADX (Returns DataFrame: ADX_14, DMP_14, DMN_14)
        adx = ta.adx(df['high'], df['low'], df['close'], length=self.adx_len)
        if adx is not None:
            df = pd.concat([df, adx], axis=1)
            # Normalize column name
            df['adx'] = df[f'ADX_{self.adx_len}']

        # ATR (For volatility-based stops)
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=self.atr_len)

        return df

    def check_signal(self, df):
        """
        Check for ENTRY signals (LONG) based on Trend Following.
        """
        if df.empty or len(df) < self.ema_long_len:
            return None, None

        curr = df.iloc[-2] # Last closed candle
        prev = df.iloc[-3]

        # 1. Trend Direction (EMA 50 > EMA 200)
        trend_up = curr['ema_50'] > curr['ema_200']

        # 2. Strong Trend Strength (ADX > 20)
        strong_trend = curr['adx'] > self.adx_threshold

        # 3. Entry Trigger:
        # Option A: Golden Cross (EMA 50 crosses above 200) - Very safe, rare signals
        # Option B: Price Pullback (Price closes above EMA 50 while Trend is UP) - More frequent
        # Let's go with Golden Cross OR Trend Continuation (Price crosses EMA 50 up)

        # Golden Cross
        golden_cross = (curr['ema_50'] > curr['ema_200']) and (prev['ema_50'] <= prev['ema_200'])

        # Price Cross over EMA 50 (Re-entry in trend)
        price_cross_ema50 = (curr['close'] > curr['ema_50']) and (prev['close'] <= prev['ema_50'])

        signal = False
        reason = ""

        if strong_trend:
            if golden_cross:
                signal = True
                reason = "Golden Cross (50/200)"
            elif trend_up and price_cross_ema50:
                signal = True
                reason = "Trend Continuation (EMA 50 Breakout)"

        if signal:
            return "LONG", {
                "ema_50": float(curr['ema_50']),
                "ema_200": float(curr['ema_200']),
                "adx": float(curr['adx']),
                "atr": float(curr['atr']),
                "price": float(curr['close']),
                "signal_reason": reason
            }

        return None, None

    def check_exit(self, df, position_side):
        """
        Check for EXIT signals based on Trend Reversal.
        """
        if df.empty:
            return False, "No Data"

        curr = df.iloc[-1] # Current candle

        # Exit if Trend breaks (Price closes below EMA 200) - "The Trend is dead"
        if position_side == "LONG":
            if curr['close'] < curr['ema_200']:
                return True, "Trend Reversal (Close < EMA 200)"

        return False, None
