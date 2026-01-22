import asyncio
import logging
from src.config import Config
from src.exchange import Exchange
from src.database import Database
from src.strategy import Strategy
from src.risk_manager import RiskManager
from src.logger_handler import SupabaseHandler
from telegram import Bot
from telegram.error import TelegramError

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, Config.LOG_LEVEL)
)

# Silence noisy HTTP logs from libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)

class MrRobotTrade:
    def __init__(self):
        self.exchange = Exchange()
        self.db = Database()
        self.strategy = Strategy()
        self.risk_manager = RiskManager()
        self.running = True
        self.current_trade = None
        self.tg_bot = None

        # Add Supabase Error Handler
        db_handler = SupabaseHandler(self.db)
        logging.getLogger().addHandler(db_handler)

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
                    if current_price is None:
                        await asyncio.sleep(10)
                        continue

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

                        if current_price is None:
                            continue

                        # Check Entry
                        entered = await self.look_for_entry(df, current_price, market)

                        # Heartbeat Log - Show monitoring activity
                        if not entered:
                            last_row = df.iloc[-1]
                            ema9 = last_row.get('ema_fast', 0)
                            ema21 = last_row.get('ema_slow', 0)
                            supertrend = last_row.get('supertrend', 0)
                            st_direction = "UP" if current_price > supertrend else "DOWN"

                            logging.info(
                                f"[{symbol}] Price: {current_price:.2f} | "
                                f"EMA9: {ema9:.2f} / EMA21: {ema21:.2f} | "
                                f"SuperTrend: {st_direction} | Status: Monitoring"
                            )

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
        symbol = self.current_trade['symbol']
        side = self.current_trade['side']
        entry_price = float(self.current_trade['entry_price'])
        # Cálculo de PnL % (Assume LONG por enquanto conforme look_for_entry)
        pnl_pct = (current_price - entry_price) / entry_price

        # 1. Recuperar Dados
        initial_stop_percent = 0.05
        if 'market_settings' in self.current_trade:
             initial_stop_percent = float(self.current_trade['market_settings'].get('stop_loss_percent', 0.05))

        # Trailing Stop Price from strategy_data
        strategy_data = self.current_trade.get('strategy_data', {})
        if strategy_data is None: strategy_data = {}
        trailing_stop_price = strategy_data.get('trailing_stop_price')

        should_exit = False
        exit_reason = ""

        # 2. Verificar Saída de Emergência (Stop Loss Inicial)
        if trailing_stop_price is None:
            if pnl_pct <= -initial_stop_percent:
                should_exit = True
                exit_reason = f"Initial Stop Loss (-{initial_stop_percent*100}%)"

        # 3. Atualizar/Verificar Trailing Stop (Lucro)
        # Ativação: Se lucrou >= 3%
        if pnl_pct >= 0.03:
            new_stop = current_price * (1 - 0.03) # Margem de 3%

            # Lógica da Catraca: Só move se for para subir o stop
            if trailing_stop_price is None or new_stop > trailing_stop_price:
                trailing_stop_price = new_stop
                strategy_data['trailing_stop_price'] = trailing_stop_price
                self.current_trade['strategy_data'] = strategy_data

                # Persistência no DB
                self.db.update_trade(self.current_trade['id'], {'strategy_data': strategy_data})
                logging.info(f"[{symbol}] Trailing Stop movido para {trailing_stop_price:.2f}")

        # Execução do Trailing Stop
        if trailing_stop_price is not None and current_price < trailing_stop_price:
            should_exit = True
            exit_reason = f"Trailing Stop Hit ({trailing_stop_price:.2f})"

        # 4. Saída Técnica (Cruzamento de Médias)
        if not should_exit:
            technical_exit, tech_reason = self.strategy.check_exit(df, side)
            if technical_exit:
                should_exit = True
                exit_reason = tech_reason

        if should_exit:
            await self.close_trade(exit_reason, current_price)

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
