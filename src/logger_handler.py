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

            log_entry = {
                'level': record.levelname,
                'module': record.name,
                'message': record.getMessage(),
                'stack_trace': stack_trace,
                'mode': Config.TRADING_MODE,
                'metadata': {
                    'filename': record.filename,
                    'lineno': record.lineno,
                    'funcName': record.funcName
                }
            }

            # Use a direct insert to avoid any dependencies on local logging
            self.db.log_system_error(log_entry)

        except Exception:
            # Silently fail if logging to DB fails to avoid app crash
            pass
