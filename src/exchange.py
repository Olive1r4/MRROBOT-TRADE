import ccxt.async_support as ccxt
import logging
import asyncio
from datetime import datetime
from src.config import Config
from src.database import Database

class Exchange:
    def __init__(self):
        self.mode = Config.TRADING_MODE
        self.timeframe = Config.TIMEFRAME
        self.db = Database()

        # Initialize CCXT Binance Futures
        exchange_config = {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
            }
        }

        if Config.BINANCE_API_KEY and Config.BINANCE_SECRET_KEY:
            exchange_config['apiKey'] = Config.BINANCE_API_KEY
            exchange_config['secret'] = Config.BINANCE_SECRET_KEY

        self.client = ccxt.binance(exchange_config)
        self.paper_balance = self._init_paper_balance()

    def _init_paper_balance(self):
        """Initialize balance logging and paper values."""
        if self.mode == 'PAPER':
            last_balance = self.db.get_latest_paper_balance()
            if last_balance is not None:
                logging.info(f"Loaded existing PAPER balance: ${last_balance}")
                return last_balance
            else:
                logging.info(f"Initializing new PAPER balance: ${Config.INITIAL_PAPER_BALANCE}")
                self.db.log_wallet({
                    'total_balance': Config.INITIAL_PAPER_BALANCE,
                    'available_balance': Config.INITIAL_PAPER_BALANCE,
                    'mode': 'PAPER'
                })
                return Config.INITIAL_PAPER_BALANCE
        return 0.0

    async def close(self):
        await self.client.close()

    async def get_candles(self, symbol, limit=300):
        """ALWAYS fetch real market data."""
        try:
            ohlcv = await self.client.fetch_ohlcv(symbol, self.timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            logging.error(f"Error fetching candles for {symbol}: {e}")
            return None

    async def get_current_price(self, symbol):
        """ALWAYS fetch real market price."""
        try:
            ticker = await self.client.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            logging.error(f"Error fetching price for {symbol}: {e}")
            return None

    async def get_balance(self):
        """Hybrid Balance Fetching."""
        if self.mode == 'LIVE':
            try:
                balance = await self.client.fetch_balance()
                # USDT balance for futures
                usdt = balance['USDT']['free']
                total = balance['USDT']['total']
                return {'free': usdt, 'total': total}
            except Exception as e:
                logging.error(f"Error fetching LIVE balance: {e}")
                return {'free': 0.0, 'total': 0.0}
        else:
            # Paper Mode
            return {'free': self.paper_balance, 'total': self.paper_balance}

    async def get_position(self, symbol):
        """Check active position for a symbol. Returns size (float)."""
        if self.mode == 'LIVE':
            try:
                positions = await self.client.fetch_positions(symbols=[symbol])
                if positions:
                    return float(positions[0]['contracts'])
                return 0.0
            except Exception as e:
                logging.error(f"Error fetching position for {symbol}: {e}")
                return 0.0
        return 0.0 # Paper mode doesn't track this yet

    async def set_leverage(self, leverage, symbol):
        """Set leverage for symbol."""
        try:
            await self.client.set_leverage(leverage, symbol)
        except Exception as e:
            logging.error(f"Error setting leverage for {symbol}: {e}")

    async def create_order(self, symbol, side, amount, params=None):
        """Hybrid Order Execution."""
        if params is None:
            params = {}

        current_price = await self.get_current_price(symbol)
        if not current_price:
            logging.error("Cannot create order: Failed to get price.")
            return None

        # Map signals to CCXT sides
        side_map = {'LONG': 'buy', 'SHORT': 'sell', 'BUY': 'buy', 'SELL': 'sell'}
        ccxt_side = side_map.get(side.upper(), side.lower())

        if self.mode == 'LIVE':
            try:
                order = await self.client.create_order(
                    symbol=symbol,
                    type='MARKET',
                    side=ccxt_side,
                    amount=amount,
                    params=params
                )
                return order
            except Exception as e:
                logging.error(f"Error creating LIVE order: {e}")
                return None
        else:
            # Paper Mode Simulation
            logging.info(f"PAPER EXECUTION: {ccxt_side.upper()} {amount} {symbol} @ {current_price}")

            # Create a fake order object structure similar to CCXT
            fake_order = {
                'id': f'paper_{int(datetime.now().timestamp())}',
                'symbol': symbol,
                'side': side.lower(),
                'type': 'market',
                'amount': amount,
                'price': current_price, # Market fill assumption
                'average': current_price,
                'status': 'closed',
                'timestamp': int(datetime.now().timestamp() * 1000),
                'info': {'msg': 'Simulated Order'}
            }
            return fake_order

    async def update_paper_balance(self, pnl):
        """Update internal paper balance after a trade close."""
        if self.mode == 'PAPER':
            self.paper_balance += pnl
            self.db.log_wallet({
                'total_balance': self.paper_balance,
                'available_balance': self.paper_balance,
                'mode': 'PAPER'
            })
            logging.info(f"Updated PAPER Balance: ${self.paper_balance:.2f}")

    def calculate_position_size(self, balance, price, leverage=5):
        """Calculate amount based on 100% bank rule and leverage."""
        # Cost = (Price * Amount) / Leverage
        # We want Cost = Balance
        # So: Balance = (Price * Amount) / Leverage
        # Amount = (Balance * Leverage) / Price

        # Apply a small safety buffer (e.g. 98% to avoid Insufficient Margin)
        usable_balance = balance * 0.98
        notional_value = usable_balance * leverage
        amount = notional_value / price
        return amount
