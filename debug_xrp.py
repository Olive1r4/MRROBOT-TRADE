
import asyncio
import os
import sys
from dotenv import load_dotenv

# Load Env
load_dotenv()

# Add src to path
sys.path.append(os.getcwd())

from src.database import Database
from src.exchange import Exchange
from src.config import Config

async def check_orphans():
    print("--- Checking Orphaned XRP Orders ---")

    db = Database()
    exchange = Exchange()

    # 1. Get DB Orders
    try:
        response = db.get_client().table('trades_mrrobot')\
            .select('*')\
            .eq('symbol', 'XRP/USDT')\
            .eq('status', 'OPEN')\
            .execute()

        db_orders = response.data
        if not db_orders:
            print("No OPEN orders for XRP in DB.")
            return

        print(f"Found {len(db_orders)} OPEN orders in DB.")

        # 2. Get Binance Open Orders
        binance_orders = await exchange.client.fetch_open_orders('XRP/USDT')
        binance_ids = {str(o['id']) for o in binance_orders}

        print(f"Found {len(binance_orders)} OPEN orders on Binance.")

        # 3. Compare
        orphan_count = 0
        for trade in db_orders:
            # Check if order_id exists column (might overlap with 'id' if stored poorly)
            # Assuming 'order_id' column or map from strategy_data

            # If trade has 'order_id' column (ideal)
            # But based on code review, we rely on strategy_data or implicit ID matching?
            # Let's check trade structure. Assuming trade['id'] is UUID, actual order ID is inside strategy_data?
            # No, 'id' on trade table is UUID. 'binance_order_id' or 'order_id' column?

            # Let's inspect ONE record to see where binance ID is stored
            # Based on previous code: trade['order_id'] ??
            # Wait, let's look at `log_trade` in database.py

            # Actually, let's assume `id` column might be UUID, and we store binance ID in `order_id` or similar.
            pass

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await exchange.client.close()

if __name__ == "__main__":
    asyncio.run(check_orphans())
