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

    async def check_btc_trend(self) -> bool:
        """
        Check if BTC is in strong downtrend (safety filter)
        Returns False if BTC is dropping too fast (block new buys)
        """
        if not Config.BTC_FILTER_ENABLED:
            return True  # Filter disabled, always allow

        try:
            # Fetch BTC candles for the configured timeframe (e.g., 1h)
            btc_symbol = 'BTC/USDT'
            limit = 2  # Current + 1 previous candle

            candles = await self.exchange.get_candles(btc_symbol, limit=limit, timeframe=Config.BTC_FILTER_TIMEFRAME)
            if not candles or len(candles) < 2:
                logging.warning("[BTC FILTER] Could not fetch BTC data, allowing trades (fail-safe)")
                return True

            # Calculate price change
            previous_close = candles[-2][4]  # Close of previous candle
            current_close = candles[-1][4]   # Close of current candle

            price_change_pct = ((current_close - previous_close) / previous_close)

            # Check if drop exceeds threshold
            if price_change_pct < Config.BTC_FILTER_THRESHOLD:
                logging.warning(
                    f"🚨 [BTC FILTER] BTC dropped {price_change_pct*100:.2f}% "
                    f"(threshold: {Config.BTC_FILTER_THRESHOLD*100:.2f}%). "
                    f"BLOCKING new BUY orders for safety."
                )
                await self.send_notification(
                    f"🛡️ **BTC Crash Protection Activated**\n\n"
                    f"BTC: {price_change_pct*100:.2f}% in {Config.BTC_FILTER_TIMEFRAME}\n"
                    f"Status: New BUY orders BLOCKED"
                )
                return False

            # All good
            logging.info(f"[BTC FILTER] BTC trend OK ({price_change_pct*100:+.2f}%)")
            return True

        except Exception as e:
            logging.error(f"[BTC FILTER] Error checking BTC trend: {e}")
            return True  # Fail-safe: allow trading if check fails

    def calculate_rsi(self, candles, period=14):
        """
        Calculate RSI (Relative Strength Index) manually
        """
        try:
            closes = [float(c[4]) for c in candles]  # Close prices

            if len(closes) < period + 1:
                return None

            # Calculate price changes
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]

            # Separate gains and losses
            gains = [d if d > 0 else 0 for d in deltas]
            losses = [-d if d < 0 else 0 for d in deltas]

            # Calculate average gain/loss (using EMA for standard RSI)
            avg_gain = sum(gains[:period]) / period
            avg_loss = sum(losses[:period]) / period

            # Calculate RSI using first smoothed values
            for i in range(period, len(gains)):
                avg_gain = (avg_gain * (period - 1) + gains[i]) / period
                avg_loss = (avg_loss * (period - 1) + losses[i]) / period

            if avg_loss == 0:
                return 100  # No losses = maximum RSI

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            return rsi

        except Exception as e:
            logging.error(f"[RSI] Error calculating RSI: {e}")
            return None

    async def check_rsi_filter(self, symbol: str) -> bool:
        """
        Check if symbol's RSI is overbought (safety filter)
        Returns False if RSI is too high (block new buys)
        """
        if not Config.RSI_FILTER_ENABLED:
            return True  # Filter disabled, always allow

        try:
            # Fetch candles for RSI calculation
            # Need period + 1 candles minimum
            limit = Config.RSI_FILTER_PERIOD + 10  # Extra buffer

            candles = await self.exchange.get_candles(symbol, limit=limit, timeframe=Config.RSI_FILTER_TIMEFRAME)
            if not candles or len(candles) < Config.RSI_FILTER_PERIOD + 1:
                logging.warning(f"[RSI FILTER] Could not fetch enough data for {symbol}, allowing trades (fail-safe)")
                return True

            # Calculate RSI
            rsi = self.calculate_rsi(candles, period=Config.RSI_FILTER_PERIOD)

            if rsi is None:
                logging.warning(f"[RSI FILTER] Could not calculate RSI for {symbol}, allowing trades (fail-safe)")
                return True

            # Check if overbought
            if rsi > Config.RSI_FILTER_THRESHOLD:
                logging.warning(
                    f"🔥 [RSI FILTER] {symbol} is overbought (RSI={rsi:.1f} > {Config.RSI_FILTER_THRESHOLD}). "
                    f"BLOCKING new BUY orders to avoid buying at top."
                )
                await self.send_notification(
                    f"🔥 **RSI Overbought Protection**\n\n"
                    f"{symbol}: RSI {rsi:.1f} (threshold: {Config.RSI_FILTER_THRESHOLD})\n"
                    f"Status: New BUY orders BLOCKED"
                )
                return False

            # All good
            logging.info(f"[RSI FILTER] {symbol} RSI OK ({rsi:.1f})")
            return True

        except Exception as e:
            logging.error(f"[RSI FILTER] Error checking RSI for {symbol}: {e}")
            return True  # Fail-safe: allow trading if check fails


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
            candles = await self.exchange.get_candles(symbol, limit=96)  # 24h of 15m candles (96 * 15m = 24h)
            if not candles:
                logging.error(f"[GRID SETUP] Failed to fetch candles for {symbol}")
                return

            # Set leverage for this symbol (Binance stores leverage per-pair)
            # This ensures all new orders use the configured leverage from database
            try:
                leverage = int(market_settings.get('leverage', 5))  # Default to 5x if not in DB
                await self.exchange.set_leverage(leverage, symbol)
                logging.info(f"[GRID SETUP] Set leverage to {leverage}x for {symbol}")
            except Exception as e:
                logging.warning(f"[GRID SETUP] Could not set leverage for {symbol}: {e} (continuing anyway)")


            # Cancel existing orders to start fresh (avoids duplication and margin issues)
            # This ensures we sync with the current correct grid parameters
            logging.info(f"[GRID SETUP] Canceling existing orders for {symbol} to align with new grid")

            # 1. Update DB functionality FIRST (Mark PENDING entries as CANCELLED)
            self.db.cancel_pending_trades(symbol)

            # 2. Cancel on Exchange - ONLY BUY ORDERS (Preserve SELLS/TPs)
            await self.exchange.cancel_all_orders(symbol, side='BUY')

            # 3. Restore existing OPEN trades (active Sell Orders) to internal state
            # This ensures we track TPs even after restart
            existing_open_trades = self.db.get_open_trades(symbol)
            restored_count = 0
            for trade in existing_open_trades:
                strategy_data = trade.get('strategy_data', {})
                sell_order_id = strategy_data.get('sell_order_id')

                if sell_order_id:
                     # Fetch order details to reconstruct pending_order object
                     order = await self.exchange.get_order(str(sell_order_id), symbol)

                     if order:
                         # Add to tracking
                         self.pending_orders[str(sell_order_id)] = {
                             'symbol': symbol,
                             'level': strategy_data.get('grid_level'),
                             'order': order,
                             'grid_cycle_id': strategy_data.get('grid_cycle_id'),
                             'entry_price': float(trade['entry_price'])
                         }
                         restored_count += 1

            if restored_count > 0:
                 logging.info(f"[GRID SETUP] Restored {restored_count} active Sell orders for {symbol}")

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

            # Check for existing open positions (filled Buy orders)
            open_trades_count = self.db.get_open_trades_count(symbol)
            allowed_new_buys = max(0, int(Config.GRID_LEVELS) - open_trades_count)

            logging.info(f"[GRID SETUP] {symbol}: existing open positions={open_trades_count}, allowed new buys={allowed_new_buys}")

            if allowed_new_buys == 0:
                 logging.warning(f"[GRID SETUP] {symbol} has reached max positions ({open_trades_count}/{Config.GRID_LEVELS}). No new BUY orders will be placed.")

            # BTC Crash Protection: Don't create new buys if BTC is crashing
            if allowed_new_buys > 0:
                btc_ok = await self.check_btc_trend()
                if not btc_ok:
                    logging.warning(f"[GRID SETUP] Skipping new BUY orders for {symbol} due to BTC crash protection")
                    logging.info(f"[GRID SETUP] Grid updated for {symbol} (Monitoring Only - BTC crash protection active)")
                    return

                # RSI Overbought Protection: Don't create new buys if symbol is overbought
                rsi_ok = await self.check_rsi_filter(symbol)
                if not rsi_ok:
                    logging.warning(f"[GRID SETUP] Skipping new BUY orders for {symbol} due to RSI overbought protection")
                    logging.info(f"[GRID SETUP] Grid updated for {symbol} (Monitoring Only - RSI overbought protection active)")
                    return


            current_price = await self.exchange.get_current_price(symbol)

            created_buys = 0
            for level in grid_levels:
                # Stop if we reached the limit of allowed new buys
                if created_buys >= allowed_new_buys:
                    break

                # Only create BUY orders for now (we don't have inventory to sell)
                if level['side'] == 'BUY':
                    if level['price'] < current_price:
                        order = await self.exchange.create_limit_order(
                            symbol=symbol,
                            side='BUY',
                            amount=level['size'],
                            price=level['price']
                        )
                        if order:
                            created_buys += 1
                    else:
                        logging.warning(f"[GRID SETUP] Skipping BUY level ${level['price']:.4f} > Current ${current_price:.4f} (Safety)")
                        order = None

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

            # Only notify if we actually created new buy orders or have pending orders
            # This prevents spam when the bot is just "monitoring" full positions
            if created_buys > 0:
                await self.send_notification(msg)
                logging.info(f"[GRID SETUP] Grid created for {symbol} with {created_buys} new BUY orders")
            else:
                # Log internally but don't annoy the user
                logging.info(f"[GRID SETUP] Grid updated for {symbol} (Monitoring Only - {open_trades_count}/{Config.GRID_LEVELS} positions filled)")

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
            # Calculate metrics for logging
            symbol_orders = [o for o in self.pending_orders.values() if o['symbol'] == symbol]
            active_buys = len([o for o in symbol_orders if o['order']['side'].lower() == 'buy'])
            active_sells = len([o for o in symbol_orders if o['order']['side'].lower() == 'sell'])

            logging.info(f"[GRID] Monitoring {symbol} | Price: ${current_price:.4f} | Open Positions: {active_sells} | Pending Buys: {active_buys}")

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
                pnl = 0.0
                try:
                    # Calculate profit based on direction
                    # If we bought (LONG), profit is Sell - Buy
                    # If we sold (SHORT), profit is Sell - Buy (which is Entry - Exit for short? No, PnL is usually Entry-Exit for Short)
                    # For Spot/Long-Only Grid:
                    if filled_order['side'].upper() == 'BUY':
                        # COMPRA preenchida -> Ciclo iniciou/continuou -> Status OPEN
                        # Atualizamos o registro existente (que estava PENDING)
                        pnl = (opposite['price'] - filled_order['price']) * filled_order['amount']

                        trade_data = {
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
                                'expected_profit': pnl
                            }
                        }
                        # Update existing cycle
                        if not self.db.update_trade_by_cycle(order_data['grid_cycle_id'], trade_data):
                            self.db.log_trade(trade_data)

                    else:
                        # VENDA preenchida (TP) -> Ciclo fechou -> Status CLOSED
                        # 1. Fechar o trade anterior no banco
                        realized_pnl = (filled_order['price'] - order_data.get('entry_price', filled_order['price'])) * filled_order['amount']
                        # Fallback for PnL if entry_price missing: estimate from spread
                        if realized_pnl == 0:
                             realized_pnl = abs(filled_order['price'] - opposite['price']) * filled_order['amount']

                        close_data = {
                            'status': 'CLOSED',
                            'exit_price': filled_order['price'],
                            'pnl': realized_pnl,
                            'updated_at': 'now()'
                        }
                        self.db.update_trade_by_cycle(order_data['grid_cycle_id'], close_data)

                        # 2. Criar NOVO registro para a ordem de recompra (Grid Infinito)
                        # Precisamos de um novo ID de ciclo para não misturar com o fechado
                        new_cycle_id = str(uuid.uuid4())

                        # Atualizar o pending_orders local com o novo ID
                        self.pending_orders[new_order['id']]['grid_cycle_id'] = new_cycle_id

                        # Inserir novo trade PENDING
                        new_trade_data = {
                            'symbol': symbol,
                            'side': 'LONG',
                            'entry_price': opposite['price'], # Preço da nova ordem Limit Buy
                            'amount': opposite['size'],
                            'status': 'PENDING',
                            'strategy_data': {
                                'strategy': 'grid_trading',
                                'grid_level': opposite['level'],
                                'grid_cycle_id': new_cycle_id,
                                'order_id': new_order['id']
                            }
                        }
                        self.db.log_trade(new_trade_data)

                        # Para o log de notificação
                        pnl = realized_pnl

                except Exception as e:
                    logging.error(f"Failed to log trade update to DB: {e}")


                logging.info(f"[GRID] Created opposite order: {opposite['side']} @ ${opposite['price']:.4f}")

                msg = (
                    f"✅ **GRID ORDER FILLED**\n\n"
                    f"🔹 Symbol: {symbol}\n"
                    f"📍 Filled: {filled_order['side'].upper()} @ ${filled_order['price']:.4f}\n"
                    f"🎯 Created: {opposite['side']} @ ${opposite['price']:.4f}\n"
                    f"💰 Expected Profit: ${pnl:.2f}"
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
