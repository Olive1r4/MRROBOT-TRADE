import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

# Activate SOL, XRP, DOGE, ADA with 5x leverage
symbols_to_activate = ['SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'ADA/USDT']

for symbol in symbols_to_activate:
    result = supabase.table('market_settings').update({
        'is_active': True,
        'leverage': 5
    }).eq('symbol', symbol).execute()

    print(f"✅ Activated {symbol} with 5x leverage")

print("\n✅ All markets activated!")
