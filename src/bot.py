import asyncio
import logging
from src.config import Config
from src.exchange import Exchange
from src.database import Database
from src.strategy import Strategy
from src.risk_manager import RiskManager
from telegram import Bot
from telegram.error import TelegramError

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=getattr(logging, Config.LOG_LEVEL)
)

class MrRobotTrade:
    def __init__(self):
        self.exchange = Exchange()
        self.db = Database()
        self.strategy = Strategy()
        self.risk_manager = RiskManager()
        self.running = True
        self.current_trade = None
        self.tg_bot = None

        if Config.TELEGRAM_BOT_TOKEN:
            self.tg_bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)

        # Load any existing OPEN trade from DB
        self._load_open_trade()

    async def send_notification(self, message):
        """Send message to Telegram."""
        if self.tg_bot and Config.TELEGRAM_CHAT_ID:
            try:
                await self.tg_bot.send_message(chat_id=Config.TELEGRAM_CHAT_ID, text=message)
            except TelegramError as e:
                logging.error(f"Telegram Error: {e}")

    def _load_open_trade(self):
        """Recover state from DB."""
        try:
            client = self.db.get_client()
            response = client.table('trades')\
                .select('*')\
                .eq('status', 'OPEN')\
                .eq('mode', Config.TRADING_MODE)\
                .limit(1)\
                .execute()

            if response.data and len(response.data) > 0:
                self.current_trade = response.data[0]
                # Try to fetch settings for this symbol
                try:
                    settings_res = client.table('market_settings').select('*').eq('symbol', self.current_trade['symbol']).execute()
                    if settings_res.data:
                        self.current_trade['market_settings'] = settings_res.data[0]
                except:
                    pass
                logging.info(f"Resumed OPEN trade: {self.current_trade['id']} ({self.current_trade['symbol']})")
        except Exception as e:
            logging.error(f"Error loading open trades: {e}")

    async def run(self):
        start_msg = f"🚀 **MrRobot Trade Started**\nMode: `{Config.TRADING_MODE}`\nSymbol check: Active Settings"
        logging.info(f"Starting MrRobot Trade [{Config.TRADING_MODE}]")
        await self.send_notification(start_msg)

        while self.running:
            try:
                # 0. Check Kill Switch (Global Safety)
                if not self.risk_manager.check_kill_switch():
                    logging.critical("🚨 System halted by Kill Switch")
                    await self.send_notification("🚨 **KILL SWITCH ACTIVATED**\nTrading halted for safety.")
                    await asyncio.sleep(300)  # Wait 5 minutes before checking again
                    continue

                # 1. Manage Existing Trade (Global Single Trade Rule)
                if self.current_trade:
                    # Fetch data only for the active symbol
                    symbol = self.current_trade['symbol']
                    candles = await self.exchange.get_candles(symbol) # Pass symbol
                    if not candles:
                        await asyncio.sleep(10)
                        continue

                    current_price = await self.exchange.get_current_price(symbol) # Pass symbol
                    df = self.strategy.parse_data(candles)
                    df = self.strategy.calculate_indicators(df)

                    await self.manage_trade(df, current_price)

                else:
                    # 2. Scanning Mode (No switch active)
                    active_markets = self.db.get_active_markets()
                    if not active_markets:
                        logging.warning("No active markets found in DB.")
                        await asyncio.sleep(60)
                        continue

                    for market in active_markets:
                        symbol = market['symbol']
                        # Fetch Data
                        candles = await self.exchange.get_candles(symbol)
                        if not candles:
                            continue

                        df = self.strategy.parse_data(candles)
                        df = self.strategy.calculate_indicators(df)
                        current_price = await self.exchange.get_current_price(symbol)

                        # Check Entry
                        entered = await self.look_for_entry(df, current_price, market)

                        if entered:
                            # SINGLE TRADE RULE: Stop scanning once we enter a trade
                            break

                        # Small delay between symbols to avoid rate limits
                        await asyncio.sleep(1)

                # Wait before next cycle
                await asyncio.sleep(60)

            except Exception as e:
                logging.error(f"Main Loop Error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(60)

    async def look_for_entry(self, df, current_price, market_settings):
        signal, data = self.strategy.check_signal(df)
        symbol = market_settings['symbol']

        if signal == "LONG":
            logging.info(f"SIGNAL DETECTED ({symbol}): {signal} at {current_price}")

            # 1. Risk Checks
            # 1.1 Check Cooldown
            if not self.risk_manager.check_cooldown(symbol):
                logging.warning(f"Entry blocked: {symbol} is in cooldown period")
                return False

            # 1.2 Calculate Size
            balance_info = await self.exchange.get_balance()
            available_balance = float(balance_info['free'])

            if available_balance < 10:
                logging.warning(f"Insufficient balance: {available_balance}")
                return False

            # 1.3 Check Daily Loss Limit
            if not self.risk_manager.check_daily_loss(available_balance):
                logging.critical("Entry blocked: Daily loss limit exceeded")
                await self.send_notification("🚨 **DAILY LOSS LIMIT EXCEEDED**\nKill Switch activated.")
                return False

            # Use dynamic leverage from market settings
            leverage = int(market_settings.get('leverage', 5))

            # Update Exchange to use this leverage (Live Mode)
            if Config.TRADING_MODE == 'LIVE':
                 await self.exchange.set_leverage(leverage, symbol)

            amount = self.exchange.calculate_position_size(available_balance, current_price, leverage)

            # 1.4 Final Validation
            is_valid, error_msg = self.risk_manager.validate_entry(symbol, leverage, amount, available_balance, current_price)
            if not is_valid:
                logging.error(f"Entry validation failed: {error_msg}")
                return False

            # 2. Execute Order
            order = await self.exchange.create_order(symbol, signal, amount)

            if order:
                # 3. Log to DB
                trade_record = {
                    'symbol': symbol,
                    'side': signal,
                    'entry_price': float(order['average']),
                    'amount': float(order['amount']),
                    'status': 'OPEN',
                    'mode': Config.TRADING_MODE,
                    'entry_reason': 'EMA Cross + SuperTrend',
                    'strategy_data': data
                }

                res = self.db.log_trade(trade_record)
                if res and res.data:
                    self.current_trade = res.data[0]
                    # Inject market settings into current_trade dict for management usage (e.g. Stop Loss)
                    self.current_trade['market_settings'] = market_settings
                    logging.info(f"Trade OPENED ({symbol}): {self.current_trade['id']}")

                    # Notify
                    msg = (
                        f"✅ **Trade OPENED**\n"
                        f"Symbol: `{symbol}`\n"
                        f"Side: `{signal}`\n"
                        f"Entry: `{order['average']}`\n"
                        f"Amt: `{order['amount']}`\n"
                        f"Lev: `{leverage}x`"
                    )
                    await self.send_notification(msg)
                    return True # Signal that we entered
        return False

    async def manage_trade(self, df, current_price):
        # 1. Check Technical Exit
        should_exit, reason = self.strategy.check_exit(df, self.current_trade['side'])

        # 2. Check Stop Loss (Dynamic)
        entry_price = float(self.current_trade['entry_price'])
        pnl_pct = (current_price - entry_price) / entry_price

        # Retrieve SL from settings or default 5%
        # Note: current_trade might not have 'market_settings' if loaded from DB freshly.
        # Ideally we fetch it, but for simplicity let's assume default or simple query if missing.
        stop_loss_pct = 0.05
        # If we had the settings loaded:
        if 'market_settings' in self.current_trade:
             stop_loss_pct = float(self.current_trade['market_settings'].get('stop_loss_percent', 0.05))

        # SL condition for LONG
        if pnl_pct <= -stop_loss_pct:
            should_exit = True
            reason = f"Stop Loss (-{stop_loss_pct*100}%)"

        if should_exit:
            await self.close_trade(reason, current_price)

    async def close_trade(self, reason, current_price):
        logging.info(f"Closing trade. Reason: {reason} | Price: {current_price}")

        # 1. Execute Close Order
        amount = float(self.current_trade['amount'])
        side = 'SELL' if self.current_trade['side'] == 'LONG' else 'BUY'
        symbol = self.current_trade['symbol']

        order = await self.exchange.create_order(symbol, side, amount)

        if order:
            # 2. Calculate Realized PnL
            # (Exit - Entry) * Amount
            entry_price = float(self.current_trade['entry_price'])
            exit_price = float(order['average'])

            # Raw PnL
            pnl = (exit_price - entry_price) * amount
            # Leveraged PnL is technically tracking the Margin change,
            # but PnL calculation above is effectively the profit in USDT.

            # 3. Update DB
            update_data = {
                'status': 'CLOSED',
                'close_price': exit_price,
                'close_time': datetime.now().isoformat(),
                'exit_reason': reason,
                'pnl': pnl,
                'pnl_percentage': (exit_price - entry_price) / entry_price * 100
            }

            self.db.update_trade(self.current_trade['id'], update_data)

            # 4. Update Paper Balance if needed
            if Config.TRADING_MODE == 'PAPER':
                await self.exchange.update_paper_balance(pnl)

            logging.info(f"Trade CLOSED. PnL: {pnl:.2f} USDT")

            # Notify
            icon = "💰" if pnl >= 0 else "🔻"
            msg = (
                f"{icon} **Trade CLOSED**\n"
                f"Symbol: `{symbol}`\n"
                f"Side: `{side}`\n"
                f"Close: `{exit_price}`\n"
                f"PnL: `{pnl:.2f} USDT` ({((exit_price - entry_price) / entry_price * 100):.2f}%)\n"
                f"Reason: `{reason}`"
            )
            await self.send_notification(msg)

            self.current_trade = None

if __name__ == "__main__":
    bot = MrRobotTrade()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        logging.info("Stopping Bot...")
    finally:
        loop.run_until_complete(bot.exchange.close())
