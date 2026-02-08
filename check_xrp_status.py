
import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

# Load Env
load_dotenv()

# Add src to path
sys.path.append(os.getcwd())

from src.database import Database
from src.exchange import Exchange

# Configure basic logging
logging.basicConfig(level=logging.INFO)

async def check():
    db = Database()
    exchange = Exchange()

    print("--- 1. Fetching OPEN trades from DB ---")
    try:
        response = db.get_client().table('trades_mrrobot')\
            .select('*')\
            .eq('symbol', 'XRP/USDT')\
            .eq('status', 'OPEN')\
            .execute()

        db_trades = response.data
        print(f"DB Count: {len(db_trades)}")
        for i, t in enumerate(db_trades):
            # Extract possible Order ID
            # Usually 'id' is UUID. Binanace ID might be in 'order_id' column or 'strategy_data'
            strat = t.get('strategy_data', {})
            cycle_id = strat.get('grid_cycle_id') if strat else 'N/A'
            print(f"Trade #{i+1}: ID={t['id']} | Date={t['created_at']} | Amt={t['amount']} | Price={t['entry_price']} | CycleID={cycle_id}")
            # Try to find Binance ID.
            # If we don't store it explicitly, we might have trouble matching unless we match by Amount/Price.

    except Exception as e:
        print(f"DB Error: {e}")

    print("\n--- 2. Fetching OPEN orders from Binance ---")
    try:
        open_orders = await exchange.client.fetch_open_orders('XRP/USDT')
        print(f"Binance Count: {len(open_orders)}")
        binance_map = {}
        for o in open_orders:
            print(f"Order: ID={o['id']} | Amt={o['amount']} | Price={o['price']} | Side={o['side']}")
            # Create a key for soft matching: side_price_amount
            key = f"{o['side'].upper()}_{float(o['price'])}_{float(o['amount'])}"
            binance_map[key] = o['id']

    except Exception as e:
        print(f"Binance Error: {e}")

    print("\n--- 3. Diagnosis ---")
    # Soft Match
    # Filter DB trades that look like SELLs (Grid Exit)
    # The Grid Bot creates 'OPEN' trades that are actually SELL limit orders (waiting to close)
    # Wait, 'OPEN' trade usually means we BOUGHT and are holding.
    # The corresponding SELL order is the 'Take Profit'.

    # If we have 5 OPEN trades, it means we hold 5 positions.
    # We should have 5 SELL orders on Binance to close them.

    # If only 4 SELL orders exist, one trade is "naked" (orphaned).

    # Let's match based on Amount/Price logic of TP.
    # Or just count.

    if len(db_trades) > len(open_orders):
        print(f"⚠️ DISCREPANCY: {len(db_trades)} trades in DB vs {len(open_orders)} orders on Binance.")
        print("One trade is missing its TP order!")

        # Identify which one
        # Strategy: For each DB trade, check if there is a corresponding SELL order
        # Logic: SELL Price approx = Entry * (1 + profit) ? OR verify grid logic.

        # Simpler: If we can't match ID, let's match Amount.
        # Check matching amounts

        binance_amts = [float(o['amount']) for o in open_orders]
        orphan_trades = []

        for t in db_trades:
            # DB records 'amount' we hold.
            db_amt = float(t['amount'])

            # Find closest amount in Binance orders (tolerate small diff)
            match = None
            for b_amt in binance_amts:
                if abs(b_amt - db_amt) < (db_amt * 0.001): # 0.1% tolerance
                    match = b_amt
                    break

            if match:
                binance_amts.remove(match) # Consumed
            else:
                print(f"❌ ORPHAN FOUND: Trade ID {t['id']} (Amt={db_amt}) has no matching order on Binance.")
                orphan_trades.append(t)

        if orphan_trades:
            print(f"\nFound {len(orphan_trades)} orphans. Fixing...")
            for orphan in orphan_trades:
                print(f"Closing orphan trade {orphan['id']} in DB (Marking CLOSED/CANCELED)")
                # Logic: If order is missing, assume it was filled or cancelled?
                # Safer to mark CLOSED to remove from Open list? Or CANCELED?
                # If we hold the bag but no order, we are exposed.
                # BUT user said "4 orders vs 5 db". Likely one filled/cancelled and DB missed.

                # Update DB - Use only valid columns
                # Move 'exit_reason' to strategy_data JSON
                orphan_strat = orphan.get('strategy_data') or {}
                orphan_strat['exit_reason'] = 'Sync Fix: Missing Binance Order'

                db.get_client().table('trades_mrrobot')\
                    .update({
                        'status': 'CLOSED',
                        'updated_at': 'now()',
                        'pnl': 0,
                        'strategy_data': orphan_strat
                    })\
                    .eq('id', orphan['id'])\
                    .execute()
                print("Fixed.")

    else:
        print("Counts match or Binance has more (extra orders?).")

    await exchange.client.close()

if __name__ == "__main__":
    asyncio.run(check())
