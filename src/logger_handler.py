import logging
import traceback
from src.config import Config

class SupabaseHandler(logging.Handler):
    """
    Custom logging handler to send error logs to Supabase.
    """
    def __init__(self, db_instance):
        super().__init__()
        self.db = db_instance
        # Only log ERROR and CRITICAL to the database to avoid spam
        self.setLevel(logging.ERROR)

    def emit(self, record):
        try:
            # Create a stack trace if an exception info is present
            stack_trace = None
            if record.exc_info:
                stack_trace = "".join(traceback.format_exception(*record.exc_info))

            # Adapt to existing table schema: id, level, message, meta, timestamp
            # We pack extra fields into 'meta' jsonb column
            db_log_entry = {
                'level': record.levelname,
                'message': record.getMessage(),
                'meta': {
                    'module': record.name,
                    'mode': Config.TRADING_MODE,
                    'stack_trace': stack_trace,
                    'file': record.filename,
                    'line': record.lineno,
                    'func': record.funcName
                }
            }

            # Use a direct insert to avoid any dependencies on local logging
            self.db.log_system_error(db_log_entry)

        except Exception:
            # Silently fail if logging to DB fails to avoid app crash
            pass
