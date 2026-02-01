import asyncio
import logging
from src.config import Config
from src.exchange import Exchange
from src.database import Database
from src.strategy import Strategy
from src.risk_manager import RiskManager
from src.logger_handler import SupabaseHandler
from datetime import datetime
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
        self.active_trades = [] # List of active trade objects
        self.MAX_OPEN_TRADES = 3
        self.MAX_EXPOSURE_PCT = 0.30 # 30% total exposure
        self.tg_bot = None

        # Add Supabase Error Handler
        db_handler = SupabaseHandler(self.db)
        logging.getLogger().addHandler(db_handler)

        if Config.TELEGRAM_BOT_TOKEN:
            self.tg_bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)

        # Load any existing OPEN trade from DB
        # Load any existing OPEN trades from DB
        self._load_open_trades()

    async def send_notification(self, message):
        """Send message to Telegram."""
        if self.tg_bot and Config.TELEGRAM_CHAT_ID:
            try:
                await self.tg_bot.send_message(chat_id=Config.TELEGRAM_CHAT_ID, text=message)
            except TelegramError as e:
                logging.error(f"Telegram Error: {e}")

    def _load_open_trades(self):
        """Recover state from DB."""
        try:
            client = self.db.get_client()
            response = client.table('trades')\
                .select('*')\
                .eq('status', 'OPEN')\
                .eq('mode', Config.TRADING_MODE)\
                .execute()

            if response.data and len(response.data) > 0:
                self.active_trades = response.data
                for trade in self.active_trades:
                    # Inject settings
                    try:
                        settings_res = client.table('market_settings').select('*').eq('symbol', trade['symbol']).execute()
                        if settings_res.data:
                            trade['market_settings'] = settings_res.data[0]
                    except:
                        pass
                    logging.info(f"Resumed OPEN trade: {trade['id']} ({trade['symbol']})")
        except Exception as e:
            logging.error(f"Error loading open trades: {e}")

    async def run(self):
        # Initial Wallet Check
        balance_info = await self.exchange.get_balance()
        total_balance = float(balance_info['total'])

        # Log to DB History for LIVE mode tracking
        self.db.log_wallet({
            'total_balance': total_balance,
            'available_balance': float(balance_info['free']),
            'mode': Config.TRADING_MODE
        })

        start_msg = (
            f"🤖 **MrRobot Trade Inicializado**\n\n"
            f"📍 **Modo:** {Config.TRADING_MODE}\n"
            f"💵 **Saldo Inicial:** ${total_balance:,.2f} USDT"
        )
        logging.info(f"Starting MrRobot Trade [{Config.TRADING_MODE}] - Balance: ${total_balance:.2f}")
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
                # 1. Manage Existing Trades
                if self.active_trades:
                    # Create a copy to iterate safely as we might remove items
                    for trade in self.active_trades[:]:
                        symbol = trade['symbol']
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

                    await self.manage_trade(df, current_price, trade)

                # 2. Scanning Mode (Only if slots available)
                if len(self.active_trades) < self.MAX_OPEN_TRADES:
                    active_markets = self.db.get_active_markets()
                    if not active_markets:
                        logging.warning("No active markets found in DB.")
                        await asyncio.sleep(15)
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

                        # Check Entry (Skip symbols already open)
                        is_open = any(t['symbol'] == symbol for t in self.active_trades)
                        if is_open:
                            continue

                        # Check Entry
                        entered = await self.look_for_entry(df, current_price, market)

                        # Heartbeat Log - Show monitoring activity
                        if not entered:
                            last_row = df.iloc[-1]
                            ema50 = last_row.get('ema_50', 0)
                            ema200 = last_row.get('ema_200', 0)
                            adx = last_row.get('adx', 0)
                            trend = "BULL" if ema50 > ema200 else "BEAR"

                            logging.info(
                                f"[{symbol}] Price: {current_price:.2f} | "
                                f"Trend: {trend} (50/200) | ADX: {adx:.1f} | Status: Monitoring"
                            )

                        if entered:
                            # If we filled the last slot, stop scanning
                            if len(self.active_trades) >= self.MAX_OPEN_TRADES:
                                break

                        # Small delay between symbols to avoid rate limits
                        await asyncio.sleep(1)

                # Wait before next cycle
                await asyncio.sleep(15)

            except Exception as e:
                logging.error(f"Main Loop Error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(15)

    async def look_for_entry(self, df, current_price, market_settings):
        signal, data = self.strategy.check_signal(df)
        symbol = market_settings['symbol']

        if signal:
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

            # --- ADVANCED DYNAMIC RISK SIZING ---

            # 1. Base Risk (1% of Equity)
            RISK_PER_TRADE = 0.01
            equity = available_balance # Using free balance as proxy for equity

            # 2. ADX Factor
            current_adx = data.get('adx', 0)
            adx_factor = 0.0
            if current_adx < 20: adx_factor = 0.0 # Should be filtered before, but safety net
            elif current_adx < 30: adx_factor = 1.0
            elif current_adx < 40: adx_factor = 0.8
            elif current_adx < 50: adx_factor = 0.6
            else: adx_factor = 0.4

            # 3. Exposure Factor (1 / (N+1))
            # Count open trades on the same side
            same_side_count = sum(1 for t in self.active_trades if t['side'] == signal)
            exposure_factor = 1.0 / (same_side_count + 1)

            # 4. Adjusted Risk Calculation
            adjusted_risk_amt = equity * RISK_PER_TRADE * adx_factor * exposure_factor

            # 5. Global Risk Cap Check (Max 2% total risk per side)
            MAX_GLOBAL_RISK_SIDE = 0.02
            current_side_risk = 0.0
            for t in self.active_trades:
                if t['side'] == signal:
                    # Estimate current risk amount of open trade
                    # We stored 'initial_risk_amt' hopefully, or approximated:
                    # If not stored, we can approximate 1% * equity (conservative)
                    current_side_risk += (equity * RISK_PER_TRADE) # Simplification if not stored

            if (current_side_risk/equity) + (adjusted_risk_amt/equity) > MAX_GLOBAL_RISK_SIDE:
                 logging.warning(f"Entry blocked: Global Risk Cap ({MAX_GLOBAL_RISK_SIDE*100}%) would be exceeded.")
                 return False

            # 6. Calculate Position Size based on Stop Distance
            # Retrieve ATR for stop distance
            atr = data.get('atr', 0)
            if atr == 0: atr = current_price * 0.01 # Fallback

            stop_distance = 2.0 * atr # 2 ATR stop

            if stop_distance == 0:
                 logging.warning("Stop distance is 0, cannot calculate size.")
                 return False

            # Size (Tokens) = Risk Amount / Stop Distance per Token
            # Example: Risk $20 / Stop $100 (per BTC) = 0.2 BTC
            amount = adjusted_risk_amt / stop_distance

            # Notional Value Check (Balance Limit)
            notional_value = amount * current_price
            max_leverage_amount = (equity * leverage) * 0.95 # 95% of max buying power

            if notional_value > max_leverage_amount:
                amount = max_leverage_amount / current_price
                logging.warning(f"Position size capped by wallet balance to {amount:.4f}")

            logging.info(f"Risk Logic: ADX={current_adx:.1f} (F={adx_factor}) | Exp={exposure_factor:.2f} | Risk=${adjusted_risk_amt:.2f} | Size={amount:.4f}")

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
                    'entry_price': float(order.get('average', current_price)),
                    'amount': float(order.get('amount', amount)),
                    'status': 'OPEN',
                    'mode': Config.TRADING_MODE,
                    'entry_reason': data.get('signal_reason', 'Trend Following'),
                    'strategy_data': data
                }

                logging.info(f"Order executed on Binance: {symbol} {signal}")

                res = self.db.log_trade(trade_record)
                if res and res.data:
                    self.active_trades.append(new_trade_obj)
                    # Inject market settings into current_trade dict for management usage (e.g. Stop Loss)
                    self.current_trade['market_settings'] = market_settings
                    logging.info(f"Trade recorded in DB: {self.current_trade['id']}")
                else:
                    logging.critical(f"🚨 FAILED TO LOG TRADE IN DB! But order is OPEN on Binance. Local state updated.")
                    new_trade_obj = trade_record
                    new_trade_obj['id'] = 'LOCAL_TEMP_ID'
                    new_trade_obj['market_settings'] = market_settings
                    self.active_trades.append(new_trade_obj)

                # Notify
                side_icon = "🟢" if signal.upper() in ['LONG', 'BUY'] else "🔴"
                notional = float(order.get('amount', amount)) * float(order.get('average', current_price))

                # Determine Risk Status Label for Notification
                adx_val = data.get('adx', 0)
                risk_label = "Normal (100%)"
                if adx_val >= 50: risk_label = "Mínimo (40%) ⚠️"
                elif adx_val >= 40: risk_label = "Reduzido (60%) ⚠️"
                elif adx_val >= 30: risk_label = "Moderado (80%)"

                msg = (
                    f"🚀 **NOVA OPERAÇÃO ABERTA**\n\n"
                    f"{side_icon} **ATIVO:** `{symbol}`\n"
                    f"⚡ **LADO:** `{signal}`\n"
                    f"💰 **ENTRADA:** `${float(order.get('average', current_price)):,.2f}`\n"
                    f"📊 **VALOR:** `${notional:,.2f} USDT`\n"
                    f"🛡️ **RISCO:** `{risk_label}` (ADX {adx_val:.1f})\n"
                    f"⚙️ **ALAVANCAGEM:** `{leverage}x`\n\n"
                    f"🎯 *Stop ATR:* {data.get('atr', 0):.2f} | *Alvo:* 1.5x"
                )
                if not res:
                    msg += "\n\n⚠️ **DATABASE ERROR:** Posição aberta mas não registrada no DB!"

                await self.send_notification(msg)
                return True # Signal that we entered
        return False

    async def manage_trade(self, df, current_price, trade):
        symbol = trade['symbol']
        side = trade['side']
        entry_price = float(trade['entry_price'])

        # PnL Calculation depending on side
        if side == 'LONG':
            pnl_pct = (current_price - entry_price) / entry_price
        else: # SHORT
            pnl_pct = (entry_price - current_price) / entry_price

        # Heartbeat Log while managing
        leverage = int(trade.get('market_settings', {}).get('leverage', 5))
        roi_pct = pnl_pct * leverage
        ts_status = f"{float(trade.get('strategy_data', {}).get('trailing_stop_price', 0)):.2f}" if trade.get('strategy_data', {}).get('trailing_stop_price') else "OFF"
        logging.info(f"[{symbol} | {side}] MANAGING | Price: {current_price:.2f} | PnL: {pnl_pct*100:.2f}% | ROI: {roi_pct*100:.2f}% | TS: {ts_status}")

        # 1. Recuperar Dados
        initial_stop_percent = 0.05
        if 'market_settings' in trade:
             initial_stop_percent = float(trade['market_settings'].get('stop_loss_percent', 0.05))

        # Trailing Stop Price from strategy_data
        strategy_data = trade.get('strategy_data', {})
        if strategy_data is None: strategy_data = {}
        trailing_stop_price = strategy_data.get('trailing_stop_price')

        should_exit = False
        exit_reason = ""

        # 2. Verificar Saída de Emergência (Stop Loss Dinâmico ATR)
        if trailing_stop_price is None:
            # Calcular Stop ATR na primeira execução se não existir
            if 'stop_loss_price' not in strategy_data:
                atr = float(strategy_data.get('atr', 0))
                # Fallbacks for old trades
                if atr == 0 and not df.empty:
                    atr = df.iloc[-1].get('atr', 0)
                if atr == 0:
                     atr = entry_price * 0.01
                # Stop = Entry - 2*ATR (for LONG)
                initial_stop = entry_price - (2.0 * atr)
                strategy_data['stop_loss_price'] = initial_stop
                # Calcular Take Profit (1.5x Risco)
                risk = entry_price - initial_stop
                if risk > 0:
                    strategy_data['take_profit_price'] = entry_price + (1.5 * risk)

                self.current_trade['strategy_data'] = strategy_data
                self.db.update_trade(self.current_trade['id'], {'strategy_data': strategy_data})
                tp_val = strategy_data.get('take_profit_price')
                tp_str = f"{tp_val:.2f}" if tp_val else "N/A"
                logging.info(f"[{symbol}] Initial Risk Setup | ATR Stop: {initial_stop:.2f} | TP: {tp_str}")

            stop_loss = strategy_data.get('stop_loss_price')
            if stop_loss:
                if side == 'LONG' and current_price <= stop_loss:
                    should_exit = True
                    exit_reason = f"ATR Stop Loss ({stop_loss:.2f})"
                elif side == 'SHORT' and current_price >= stop_loss:
                    should_exit = True
                    exit_reason = f"ATR Stop Loss ({stop_loss:.2f})"

        # 3. Take Profit Fixo (1.5x)
        take_profit = strategy_data.get('take_profit_price')
        if take_profit:
            if side == 'LONG' and current_price >= take_profit:
                 should_exit = True
                 exit_reason = f"Take Profit Target (1.5x) ({take_profit:.2f})"
            elif side == 'SHORT' and current_price <= take_profit:
                 should_exit = True
                 exit_reason = f"Take Profit Target (1.5x) ({take_profit:.2f})"

        # 4. Trailing Stop (Breakeven)
        # Se lucrou 1x o risco, move pro zero a zero
        if trailing_stop_price is None and 'stop_loss_price' in strategy_data:
            stop_price = float(strategy_data['stop_loss_price'])
            risk_amount = entry_price - stop_price

            # Breakeven Move Logic
            should_move = False
            new_stop = 0

            if side == 'LONG' and current_price >= (entry_price + risk_amount):
                 new_stop = entry_price * 1.001
                 should_move = True
            elif side == 'SHORT' and current_price <= (entry_price - risk_amount):
                 new_stop = entry_price * 0.999
                 should_move = True

            if should_move:
                trailing_stop_price = new_stop
                strategy_data['trailing_stop_price'] = trailing_stop_price
                trade['strategy_data'] = strategy_data
                self.db.update_trade(trade['id'], {'strategy_data': strategy_data})

                msg = (
                    f"🛡️ **STOP MOVIDO PARA BREAKEVEN**\n\n"
                    f"🔹 **Ativo:** {symbol}\n"
                    f"🔒 **Novo Stop:** ${new_stop:,.2f} (Entrada)\n"
                    f"📈 **Lucro Atual:** {pnl_pct*100:.2f}%"
                )
                await self.send_notification(msg)
                logging.info(f"[{symbol}] Moved to Breakeven: {new_stop:.2f}")

        # Execução do Trailing Stop (se já estiver ativo)
        if trailing_stop_price is not None:
            if side == 'LONG' and current_price < trailing_stop_price:
                should_exit = True
                exit_reason = f"Trailing Stop Hit ({trailing_stop_price:.2f})"
            elif side == 'SHORT' and current_price > trailing_stop_price:
                should_exit = True
                exit_reason = f"Trailing Stop Hit ({trailing_stop_price:.2f})"

        # 4. Saída Técnica (Cruzamento de Médias)
        if not should_exit:
            technical_exit, tech_reason = self.strategy.check_exit(df, side)
            if technical_exit:
                should_exit = True
                exit_reason = tech_reason

        if should_exit:
            await self.close_trade(exit_reason, current_price, trade)

    async def close_trade(self, reason, current_price, trade):
        logging.info(f"Closing trade. Reason: {reason} | Price: {current_price}")

        # 1. Execute Close Order
        amount = float(trade['amount'])
        side_to_close = 'SELL' if trade['side'] == 'LONG' else 'BUY'
        symbol = trade['symbol']

        try:
            order = await self.exchange.create_order(symbol, side_to_close, amount, params={'reduceOnly': True})

            # 2. If order failed, check if position already closed
            if not order and Config.TRADING_MODE == 'LIVE':
                logging.warning(f"Close order failed for {symbol}. Checking if position already closed on Binance...")
                pos_size = await self.exchange.get_position(symbol)
                if pos_size == 0:
                    logging.info(f"Position for {symbol} is already 0 on Binance. Synchronizing local state to CLOSED.")
                    # Create a dummy order object to proceed with closing
                    order = {
                        'average': current_price,
                        'amount': amount,
                        'status': 'closed',
                        'info': {'msg': 'Auto-sync: Position was already closed'}
                    }
                else:
                    logging.error(f"Position {pos_size} still exists for {symbol}. Will retry next cycle.")
                    return

            # fallback exit price
            exit_price = current_price
            if order and order.get('average'):
                exit_price = float(order['average'])
            elif order and order.get('price'):
                exit_price = float(order['price'])

            # 3. Calculate Realized PnL
            entry_price = float(trade['entry_price'])
            pnl = (exit_price - entry_price) * amount if trade['side'] == 'LONG' else (entry_price - exit_price) * amount

            # 4. Update DB
            update_data = {
                'status': 'CLOSED',
                'close_price': exit_price,
                'close_time': datetime.now().isoformat(),
                'exit_reason': reason,
                'pnl': pnl,
                'pnl_percentage': (pnl / (entry_price * amount)) * 100 if entry_price != 0 else 0
            }

            self.db.update_trade(trade['id'], update_data)

            # 5. Update/Log Balance
            if Config.TRADING_MODE == 'PAPER':
                await self.exchange.update_paper_balance(pnl)
            else:
                new_bal = await self.exchange.get_balance()
                self.db.log_wallet({
                    'total_balance': float(new_bal['total']),
                    'available_balance': float(new_bal['free']),
                    'mode': 'LIVE'
                })

            logging.info(f"Trade CLOSED. PnL: {pnl:.2f} USDT")

            # Notify
            res_icon = "💰" if pnl >= 0 else "🔻"
            res_text = "LUCRO" if pnl >= 0 else "PREJUÍZO"

            msg = (
                f"{res_icon} **OPERAÇÃO FINALIZADA**\n\n"
                f"🔹 **Ativo:** {symbol}\n"
                f"🏁 **Saída:** ${exit_price:,.2f}\n"
                f"💵 **PnL:** ${pnl:,.2f} USDT ({((exit_price - entry_price) / entry_price * 100):.2f}%)\n"
                f"📝 **Motivo:** {reason}"
            )
            await self.send_notification(msg)

            # Remove from active trades list using list comprehension filter
            self.active_trades = [t for t in self.active_trades if t['id'] != trade['id']]
        except Exception as e:
            logging.error(f"Error in close_trade process: {e}")

if __name__ == "__main__":
    bot = MrRobotTrade()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        logging.info("Stopping Bot...")
    finally:
        loop.run_until_complete(bot.exchange.close())
