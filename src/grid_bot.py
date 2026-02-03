import asyncio
import logging
from src.config import Config
from src.exchange import Exchange
from src.database import Database
from src.grid_strategy import GridStrategy
from src.risk_manager import RiskManager
from src.logger_handler import SupabaseHandler
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
import uuid

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, Config.LOG_LEVEL)
)

# Silence noisy HTTP logs from libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)

class GridTradingBot:
    def __init__(self):
        self.exchange = Exchange()
        self.db = Database()
        self.grid_strategy = GridStrategy(
            grid_levels=int(Config.GRID_LEVELS),
            grid_spacing_pct=float(Config.GRID_SPACING_PCT),
            profit_pct=float(Config.GRID_PROFIT_PCT)
        )
        self.risk_manager = RiskManager()
        self.running = True

        # Grid state tracking
        self.active_grids = {}  # {symbol: {'range': (low, high), 'levels': [...], 'last_rebalance': timestamp}}
        self.pending_orders = {}  # {order_id: order_data}
        self.completed_cycles = []  # Track completed buy-sell cycles

        self.tg_bot = None

        # Add Supabase Error Handler
        db_handler = SupabaseHandler(self.db)
        logging.getLogger().addHandler(db_handler)

        if Config.TELEGRAM_BOT_TOKEN:
            self.tg_bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)

    async def send_notification(self, message):
        """Send message to Telegram."""
        if self.tg_bot and Config.TELEGRAM_CHAT_ID:
            try:
                await self.tg_bot.send_message(chat_id=Config.TELEGRAM_CHAT_ID, text=message)
            except TelegramError as e:
                logging.error(f"Telegram Error: {e}")

    async def run(self):
        # Initial Wallet Check
        balance_info = await self.exchange.get_balance()
        total_balance = float(balance_info['total'])

        # Log to DB
        self.db.log_wallet({
            'total_balance': total_balance,
            'available_balance': float(balance_info['free']),
            'mode': Config.TRADING_MODE
        })

        start_msg = (
            f"🤖 **Grid Trading Bot Iniciado v3.0**\n\n"
            f"📍 **Modo:** {Config.TRADING_MODE}\n"
            f"💵 **Saldo Inicial:** ${total_balance:,.2f} USDT\n"
            f"📊 **Grid Levels:** {Config.GRID_LEVELS}\n"
            f"📏 **Spacing:** {float(Config.GRID_SPACING_PCT)*100:.2f}%\n"
            f"🎯 **Profit Target:** {float(Config.GRID_PROFIT_PCT)*100:.2f}%"
        )
        logging.info(f"Starting Grid Trading Bot [{Config.TRADING_MODE}] - Balance: ${total_balance:.2f}")
        await self.send_notification(start_msg)

        while self.running:
            try:
                # 0. Check Kill Switch
                if not self.risk_manager.check_kill_switch():
                    logging.critical("🚨 System halted by Kill Switch")
                    await self.send_notification("🚨 **KILL SWITCH ACTIVATED**\nTrading halted for safety.")
                    await asyncio.sleep(300)
                    continue

                # 0.5 Update Wallet Balance (Live monitoring)
                try:
                    balance_info = await self.exchange.get_balance()
                    self.db.log_wallet({
                        'total_balance': float(balance_info['total']),
                        'available_balance': float(balance_info['free']),
                        'mode': Config.TRADING_MODE
                    })
                except Exception as e:
                    logging.error(f"Error updating wallet balance: {e}")

                # 1. Get active markets
                active_markets = self.db.get_active_markets()
                if not active_markets:
                    logging.warning("No active markets found in DB.")
                    await asyncio.sleep(60)
                    continue

                # 2. For each market, manage grid
                for market in active_markets:
                    symbol = market['symbol']

                    # Check if grid exists for this symbol
                    if symbol not in self.active_grids:
                        # Setup new grid
                        await self.setup_grid(symbol, market)
                    else:
                        # Monitor existing grid
                        await self.monitor_grid(symbol, market)

                    # Small delay between symbols
                    await asyncio.sleep(2)

                # 3. Check for rebalancing every hour
                await asyncio.sleep(60)  # Main loop delay

            except Exception as e:
                logging.error(f"Main Loop Error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(60)

    async def setup_grid(self, symbol: str, market_settings: dict):
        """
        Create initial grid for a symbol
        """
        try:
            logging.info(f"[GRID SETUP] Initializing grid for {symbol}")

            # Fetch candles for range calculation
            candles = await self.exchange.get_candles(symbol, limit=96)  # 24h of 15m candles
            if not candles:
                logging.error(f"[GRID SETUP] Failed to fetch candles for {symbol}")
                return

            # Cancel existing orders to start fresh (avoids duplication and margin issues)
            # This ensures we sync with the current correct grid parameters
            logging.info(f"[GRID SETUP] Canceling existing orders for {symbol} to align with new grid")

            # 1. Update DB functionality FIRST (Mark PENDING entries as CANCELLED)
            self.db.cancel_pending_trades(symbol)

            # 2. Cancel on Exchange - ONLY BUY ORDERS (Preserve SELLS/TPs)
            await self.exchange.cancel_all_orders(symbol, side='BUY')

            # Calculate range
            range_low, range_high, mid_price = self.grid_strategy.calculate_grid_range(candles)

            # Get balance
            balance_info = await self.exchange.get_balance()
            available_balance = float(balance_info['free'])

            # Calculate capital per level
            # Divide available balance by number of symbols and grid levels
            capital_per_level = float(Config.CAPITAL_PER_GRID)

            # Generate grid levels
            grid_levels = self.grid_strategy.generate_grid_levels(
                mid_price, range_low, range_high, capital_per_level
            )

            # Store grid state
            self.active_grids[symbol] = {
                'range': (range_low, range_high),
                'mid_price': mid_price, # Store for deviation check
                'levels': grid_levels,
                'last_rebalance': datetime.now(),
                'market_settings': market_settings
            }

            # Create limit orders for each level
            # For now, we'll create BUY orders below mid and SELL orders above
            # In a full implementation, we'd need inventory management

            current_price = await self.exchange.get_current_price(symbol)

            for level in grid_levels:
                # Only create BUY orders for now (we don't have inventory to sell)
                if level['side'] == 'BUY' and level['price'] < current_price:
                    order = await self.exchange.create_limit_order(
                        symbol=symbol,
                        side='BUY',
                        amount=level['size'],
                        price=level['price']
                    )

                    if order:
                        grid_cycle_id = str(uuid.uuid4())
                        self.pending_orders[order['id']] = {
                            'symbol': symbol,
                            'level': level['level'],
                            'order': order,
                            'grid_cycle_id': grid_cycle_id
                        }

                        # Save to database (Best effort)
                        try:
                            self.db.log_trade({
                                'symbol': symbol,
                                'side': 'LONG',  # Grid always starts with BUY
                                'entry_price': level['price'],
                                'amount': order['amount'],  # Use actual amount from exchange (handles truncation)
                                'status': 'PENDING',
                                'strategy_data': {
                                    'strategy': 'grid_trading',
                                    'grid_level': level['level'],
                                    'grid_cycle_id': grid_cycle_id,
                                    'order_id': order['id']
                                }
                            })
                        except Exception as e:
                            logging.error(f"Failed to log trade to DB (continuing anyway): {e}")

            msg = (
                f"📊 **GRID CRIADO: {symbol}**\n\n"
                f"📏 Range: ${range_low:.4f} - ${range_high:.4f}\n"
                f"🎯 Mid Price: ${mid_price:.4f}\n"
                f"📈 Levels: {len(grid_levels)}\n"
                f"💰 Capital/Level: ${capital_per_level:.2f}"
            )
            await self.send_notification(msg)
            logging.info(f"[GRID SETUP] Grid created for {symbol} with {len(grid_levels)} levels")

        except Exception as e:
            logging.error(f"[GRID SETUP] Error setting up grid for {symbol}: {e}")
            import traceback
            traceback.print_exc()

    async def monitor_grid(self, symbol: str, market_settings: dict):
        """
        Monitor grid orders and create opposite orders when filled
        """
        try:
            grid_data = self.active_grids[symbol]
            current_price = await self.exchange.get_current_price(symbol)

            if not current_price:
                return

            # Check if rebalancing needed
            # Check if rebalancing needed
            if self.grid_strategy.should_rebalance(
                current_price,
                grid_data['range'],
                mid_price=grid_data.get('mid_price')
            ):
                logging.info(f"[GRID] Rebalancing needed for {symbol}")
                # 1. Update DB: Cancel old pending trades
                self.db.cancel_pending_trades(symbol)

                # 2. Exchange: Cancel only BUY orders (keep TPs)
                await self.exchange.cancel_all_orders(symbol, side='BUY')

                # 3. Clear pending orders tracking locally
                # We need to filter out orders that were kept (if any) or just clear all BUYs
                # Since we only cancelled BUY orders, we must preserve SELL (TP) orders in our tracker
                self.pending_orders = {
                    k: v for k, v in self.pending_orders.items()
                    if v['symbol'] != symbol or v['order']['side'].upper() != 'BUY'
                }

                # 4. Remove from active grids (will trigger re-setup in next loop)
                del self.active_grids[symbol]
                return

            # Check open orders (in LIVE mode)

            # Check open orders (in LIVE mode)
            if Config.TRADING_MODE == 'LIVE':
                open_orders = await self.exchange.get_open_orders(symbol)

                if open_orders is None:
                    logging.warning(f"[GRID] Failed to fetch open orders for {symbol}. Skipping cycle.")
                    return

                # Compare with pending orders to find filled ones
                open_order_ids = {order['id'] for order in open_orders}

                for order_id, order_data in list(self.pending_orders.items()):
                    if order_data['symbol'] != symbol:
                        continue

                    # If order not in open orders, it was filled
                    if order_id not in open_order_ids:
                        logging.info(f"[GRID] Order filled: {order_id}")
                        await self.handle_filled_order(order_data)
                        del self.pending_orders[order_id]

            # In PAPER mode, we'd simulate fills based on price crossing levels
            # For now, just log monitoring
            logging.info(f"[GRID] Monitoring {symbol} | Price: ${current_price:.4f} | Pending Orders: {len([o for o in self.pending_orders.values() if o['symbol'] == symbol])}")

        except Exception as e:
            logging.error(f"[GRID] Error monitoring grid for {symbol}: {e}")

    async def handle_filled_order(self, order_data: dict):
        """
        Handle a filled grid order by creating opposite order
        """
        try:
            filled_order = order_data['order']
            symbol = order_data['symbol']

            # Calculate opposite order
            opposite = self.grid_strategy.calculate_opposite_order({
                'side': filled_order['side'].upper(),
                'price': filled_order['price'],
                'size': filled_order['amount'],
                'level': order_data['level']
            })

            # Create opposite limit order
            new_order = await self.exchange.create_limit_order(
                symbol=symbol,
                side=opposite['side'],
                amount=opposite['size'],
                price=opposite['price']
            )

            if new_order:
                self.pending_orders[new_order['id']] = {
                    'symbol': symbol,
                    'level': opposite['level'],
                    'order': new_order,
                    'grid_cycle_id': order_data['grid_cycle_id'],
                    'entry_price': opposite['entry_price']
                }

                # Save BUY execution and SELL order creation to DB
                try:
                    profit = (opposite['price'] - filled_order['price']) * filled_order['amount']

                    # Update the BUY trade as filled
                    self.db.log_trade({
                        'symbol': symbol,
                        'side': 'LONG',
                        'entry_price': filled_order['price'],
                        'amount': filled_order['amount'],
                        'status': 'OPEN',
                        'strategy_data': {
                            'strategy': 'grid_trading',
                            'grid_level': order_data['level'],
                            'grid_cycle_id': order_data['grid_cycle_id'],
                            'sell_order_id': new_order['id'],
                            'expected_profit': profit
                        }
                    })
                except Exception as e:
                    logging.error(f"Failed to log trade update to DB: {e}")

                logging.info(f"[GRID] Created opposite order: {opposite['side']} @ ${opposite['price']:.4f}")

                msg = (
                    f"✅ **GRID ORDER FILLED**\n\n"
                    f"🔹 Symbol: {symbol}\n"
                    f"📍 Filled: {filled_order['side'].upper()} @ ${filled_order['price']:.4f}\n"
                    f"🎯 Created: {opposite['side']} @ ${opposite['price']:.4f}\n"
                    f"💰 Expected Profit: ${profit:.2f}"
                )
                await self.send_notification(msg)

        except Exception as e:
            logging.error(f"[GRID] Error handling filled order: {e}")

if __name__ == "__main__":
    bot = GridTradingBot()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        logging.info("Stopping Bot...")
    finally:
        loop.run_until_complete(bot.exchange.close())
