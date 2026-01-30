import pandas as pd
import pandas_ta as ta

class Strategy:
    def __init__(self):
        # Mean Reversion Scalping Setup
        self.bb_length = 20
        self.bb_std = 2.0
        self.rsi_length = 14

    def parse_data(self, ohlcv):
        """Convert CCXT ohlcv to Pandas DataFrame."""
        if not ohlcv or len(ohlcv) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def calculate_indicators(self, df):
        """Calculate Bollinger Bands and RSI."""
        if df.empty or len(df) < self.bb_length:
            return df

        # Bollinger Bands
        bb = ta.bbands(df['close'], length=self.bb_length, std=self.bb_std)
        if bb is not None:
            df = pd.concat([df, bb], axis=1)
            # Normalize names (Pandas TA uses BBL_20_2.0, BBM_20_2.0, BBU_20_2.0)
            # Safer approach: access by position (Lower, Mid, Upper are usually first 3)
            # pandas_ta bbands returns: BBL, BBM, BBU, BBB, BBP
            df['bb_lower'] = bb.iloc[:, 0]
            df['bb_middle'] = bb.iloc[:, 1]
            df['bb_upper'] = bb.iloc[:, 2]

        # RSI
        df['rsi'] = ta.rsi(df['close'], length=self.rsi_length)

        return df

    def check_signal(self, df):
        """
        Check for ENTRY signals (LONG) based on Mean Reversion.
        Entry: Close < Lower Band (Dip) AND RSI < 30 (Oversold)
        """
        if df.empty or len(df) < self.bb_length:
            return None, None

        # Signals are checked on the last closed candle
        curr = df.iloc[-2]

        # Conditions
        dip = curr['close'] < curr['bb_lower']
        oversold = curr['rsi'] < 30

        if dip and oversold:
            return "LONG", {
                "bb_lower": float(curr['bb_lower']),
                "bb_middle": float(curr['bb_middle']),
                "rsi": float(curr['rsi']),
                "price": float(curr['close'])
            }

        return None, None

    def check_exit(self, df, position_side):
        """
        Check for EXIT signals based on Mean Reversion.
        Exit: Price >= Middle Band (Return to mean) OR RSI > 70
        """
        if df.empty or len(df) < 1:
            return False, "No Data"

        # For exits, we can use the current price (last candle in DF)
        curr = df.iloc[-1]

        if position_side == "LONG":
            exit_condition = (curr['close'] >= curr['bb_middle']) or (curr['rsi'] > 70)
            if exit_condition:
                reason = "Mean Reversion (BB Middle)" if curr['close'] >= curr['bb_middle'] else "RSI Overbought (>70)"
                return True, reason

        return False, None
