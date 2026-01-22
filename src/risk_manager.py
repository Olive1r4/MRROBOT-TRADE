from src.database import Database
from src.config import Config
from datetime import datetime, timezone, timedelta
import logging

class RiskManager:
    def __init__(self):
        self.db = Database()

    def check_kill_switch(self):
        """Check if system is active. Returns False if kill switch is activated."""
        try:
            client = self.db.get_client()
            response = client.table('circuit_breaker')\
                .select('is_system_active')\
                .eq('id', 1)\
                .execute()

            if response.data and len(response.data) > 0:
                is_active = response.data[0]['is_system_active']
                if not is_active:
                    logging.warning("🚨 KILL SWITCH ACTIVATED - System is disabled")
                return is_active
            return True
        except Exception as e:
            logging.error(f"Error checking kill switch: {e}")
            return False

    def check_daily_loss(self, current_balance):
        """
        Check if daily loss exceeds threshold.
        If exceeded, activates kill switch and returns False.
        """
        try:
            client = self.db.get_client()

            # Get circuit breaker settings
            cb_response = client.table('circuit_breaker')\
                .select('max_daily_loss_percent')\
                .eq('id', 1)\
                .execute()

            if not cb_response.data:
                logging.warning("Circuit breaker settings not found")
                return True

            max_loss_pct = float(cb_response.data[0]['max_daily_loss_percent'])

            # Calculate today's start (00:00 UTC)
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

            # Get all closed trades from today
            trades_response = client.table('trades')\
                .select('pnl')\
                .eq('status', 'CLOSED')\
                .eq('mode', Config.TRADING_MODE)\
                .gte('close_time', today_start.isoformat())\
                .execute()

            if not trades_response.data:
                return True

            # Calculate total PnL for today
            total_pnl = sum(float(trade['pnl']) for trade in trades_response.data if trade['pnl'])

            # Check if loss exceeds threshold
            max_loss_amount = current_balance * max_loss_pct

            if total_pnl < 0 and abs(total_pnl) >= max_loss_amount:
                logging.critical(f"🚨 DAILY LOSS LIMIT EXCEEDED: {total_pnl:.2f} USDT ({(total_pnl/current_balance)*100:.2f}%)")

                # Activate kill switch
                client.table('circuit_breaker')\
                    .update({'is_system_active': False, 'updated_at': datetime.now(timezone.utc).isoformat()})\
                    .eq('id', 1)\
                    .execute()

                return False

            return True
        except Exception as e:
            logging.error(f"Error checking daily loss: {e}")
            return True

    def check_cooldown(self, symbol):
        """
        Check if symbol is in cooldown period.
        Returns False if last trade was closed less than cooldown_minutes ago.
        """
        try:
            client = self.db.get_client()

            # Get cooldown settings
            cb_response = client.table('circuit_breaker')\
                .select('cooldown_minutes')\
                .eq('id', 1)\
                .execute()

            if not cb_response.data:
                logging.warning("Circuit breaker settings not found")
                return True

            cooldown_minutes = int(cb_response.data[0]['cooldown_minutes'])

            # Get last closed trade for this symbol
            trades_response = client.table('trades')\
                .select('close_time')\
                .eq('symbol', symbol)\
                .eq('status', 'CLOSED')\
                .eq('mode', Config.TRADING_MODE)\
                .order('close_time', desc=True)\
                .limit(1)\
                .execute()

            if not trades_response.data:
                return True

            last_close_time = datetime.fromisoformat(trades_response.data[0]['close_time'].replace('Z', '+00:00'))
            time_since_close = datetime.now(timezone.utc) - last_close_time

            if time_since_close < timedelta(minutes=cooldown_minutes):
                remaining = cooldown_minutes - (time_since_close.total_seconds() / 60)
                logging.warning(f"⏳ COOLDOWN ACTIVE for {symbol}: {remaining:.1f} minutes remaining")
                return False

            return True
        except Exception as e:
            logging.error(f"Error checking cooldown: {e}")
            return True

    def validate_entry(self, symbol, leverage, amount, balance, price):
        """
        Validate entry parameters before executing order.
        Returns (is_valid, error_message)
        """
        try:
            # 1. Check leverage limit
            if leverage > 5:
                return False, f"Leverage {leverage}x exceeds maximum allowed (5x)"

            # 2. Check if order size is valid
            notional_value = amount * price
            required_margin = notional_value / leverage

            # Add 2% buffer for fees and slippage
            required_margin_with_buffer = required_margin * 1.02

            if required_margin_with_buffer > balance:
                return False, f"Insufficient balance: Required {required_margin_with_buffer:.2f}, Available {balance:.2f}"

            # 3. Sanity check: minimum order size
            if notional_value < 10:
                return False, f"Order size too small: {notional_value:.2f} USDT (min 10 USDT)"

            return True, "OK"
        except Exception as e:
            logging.error(f"Error validating entry: {e}")
            return False, f"Validation error: {str(e)}"
