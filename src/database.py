from supabase import create_client, Client
from src.config import Config
import logging

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            try:
                cls._instance.client: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                logging.info("Connected to Supabase successfully.")
            except Exception as e:
                logging.error(f"Failed to connect to Supabase: {e}")
                raise e
        return cls._instance

    def get_client(self) -> Client:
        return self.client

    def log_trade(self, trade_data: dict):
        try:
            db = self.get_client()
            response = db.table('trades_mrrobot').insert(trade_data).execute()
            return response
        except Exception as e:
            logging.error(f"Error logging trade: {e}")
            return None

    def update_trade(self, trade_id: str, update_data: dict):
        try:
            db = self.get_client()
            response = db.table('trades_mrrobot').update(update_data).eq('id', trade_id).execute()
            return response
        except Exception as e:
            logging.error(f"Error updating trade: {e}")
            return None

    def cancel_pending_trades(self, symbol: str):
        try:
            db = self.get_client()
            # Update all 'PENDING' trades for this symbol to 'CANCELLED'
            response = db.table('trades_mrrobot')\
                .update({'status': 'CANCELLED'})\
                .eq('symbol', symbol)\
                .eq('status', 'PENDING')\
                .execute()
            return response
        except Exception as e:
            logging.error(f"Error cancelling pending trades for {symbol}: {e}")
            return None

    def log_wallet(self, wallet_data: dict):
        try:
            db = self.get_client()
            # Only keep history, don't update existing rows usually for history
            response = db.table('wallet_logs_mrrobot').insert(wallet_data).execute()
            return response
        except Exception as e:
            logging.error(f"Error logging wallet history: {e}")
            return None

    def get_latest_paper_balance(self):
        try:
            db = self.get_client()
            # Get the most recent wallet history entry for PAPER mode
            response = db.table('wallet_logs_mrrobot')\
                .select('total_balance')\
                .eq('mode', 'PAPER')\
                .order('timestamp', desc=True)\
                .limit(1)\
                .execute()

            if response.data and len(response.data) > 0:
                return float(response.data[0]['total_balance'])
            return None
        except Exception as e:
            logging.error(f"Error fetching paper balance: {e}")
            return None

    def get_active_markets(self):
        """Fetch all active markets from settings."""
        try:
            db = self.get_client()
            response = db.table('market_settings')\
                .select('*')\
                .eq('is_active', True)\
                .execute()
            return response.data if response.data else []
        except Exception as e:
            logging.error(f"Error fetching active markets: {e}")
            return []

    def log_system_error(self, log_data: dict):
        """Log system errors to the database."""
        try:
            db = self.get_client()
            db.table('logs_mrrobot').insert(log_data).execute()
        except:
            # We don't use logging.error here to avoid infinite loops if DB is down
            pass
