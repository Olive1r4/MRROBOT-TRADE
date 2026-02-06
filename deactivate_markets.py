import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

# Deactivate all
symbols = ['SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'ADA/USDT']

for symbol in symbols:
    result = supabase.table('market_settings').update({
        'is_active': False
    }).eq('symbol', symbol).execute()

    print(f"❌ Deactivated {symbol}")

print("\n✅ All markets deactivated. You can now choose which ones to activate.")
