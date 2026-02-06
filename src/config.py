import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # System
    TRADING_MODE = os.getenv('TRADING_MODE', 'PAPER').upper()
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # Binance
    BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
    BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

    # Strategy
    TIMEFRAME = os.getenv('TIMEFRAME', '15m')
    INITIAL_PAPER_BALANCE = float(os.getenv('INITIAL_PAPER_BALANCE', 50.0))

    # Grid Trading Config
    GRID_LEVELS = os.getenv('GRID_LEVELS', '5')
    GRID_SPACING_PCT = os.getenv('GRID_SPACING_PCT', '0.005')  # 0.5%
    GRID_PROFIT_PCT = os.getenv('GRID_PROFIT_PCT', '0.005')    # 0.5%
    GRID_REBALANCE_THRESHOLD = float(os.getenv('GRID_REBALANCE_THRESHOLD', '0.02')) # 2% deviation
    CAPITAL_PER_GRID = os.getenv('CAPITAL_PER_GRID', '10.0')  # $10 per level

    # 3. Risk Management
    STOP_LOSS_PERCENT = os.getenv('STOP_LOSS_PERCENT', '0.02')  # 2%
    REBALANCE_THRESHOLD = os.getenv('REBALANCE_THRESHOLD', '0.10')  # 10%

    # BTC Trend Filter (Safety)
    BTC_FILTER_ENABLED = os.getenv('BTC_FILTER_ENABLED', 'false').lower() == 'true'
    BTC_FILTER_THRESHOLD = float(os.getenv('BTC_FILTER_THRESHOLD', '-0.03'))  # -3%
    BTC_FILTER_TIMEFRAME = os.getenv('BTC_FILTER_TIMEFRAME', '1h')

    # RSI Filter (Smart entry zone - buy only in healthy range)
    RSI_FILTER_ENABLED = os.getenv('RSI_FILTER_ENABLED', 'false').lower() == 'true'
    RSI_BUY_LOW = float(os.getenv('RSI_BUY_LOW', '35'))  # Lower bound for entry
    RSI_BUY_HIGH = float(os.getenv('RSI_BUY_HIGH', '60'))  # Upper bound for entry
    RSI_FILTER_TIMEFRAME = os.getenv('RSI_FILTER_TIMEFRAME', '15m')
    RSI_FILTER_PERIOD = int(os.getenv('RSI_FILTER_PERIOD', '14'))

    # Dynamic Range Adjustment (Stop Loss Alternative)
    RANGE_STOP_ENABLED = os.getenv('RANGE_STOP_ENABLED', 'false').lower() == 'true'
    RANGE_STOP_THRESHOLD = float(os.getenv('RANGE_STOP_THRESHOLD', '0.05'))  # 5%

    @staticmethod
    def validate():
        if Config.TRADING_MODE == 'LIVE':
            if not Config.BINANCE_API_KEY or not Config.BINANCE_SECRET_KEY:
                raise ValueError("Binance API credentials are required for LIVE mode.")

        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            raise ValueError("Supabase credentials are required.")

Config.validate()
