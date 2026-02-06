import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

# Check market settings
markets = supabase.table('market_settings').select('*').execute()

print("Market Settings:")
for m in markets.data:
    print(f"  {m['symbol']}: is_active={m['is_active']}, leverage={m.get('leverage', 'N/A')}")
