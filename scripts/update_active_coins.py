
import asyncio
import os
import sys

# Adicionar o diretório raiz ao path para importar src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.database import Database

NEW_COINS = [
    # Alta Liquidez e Volatilidade
    "SOLUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT",
    "RENDERUSDT",  # RNDR migrou para RENDER na Binance
    "DOTUSDT", "POLUSDT",  # MATIC migrou para POL na Binance
    "INJUSDT", "FETUSDT",

    # Momento
    "SUIUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "TAOUSDT"
]

async def update_coins():
    print("🚀 Atualizando lista de moedas Sniper...")
    config = Config()
    db = Database(config)

    # Obter moedas já existentes
    active_symbols = await db.get_active_symbols()
    existing_list = [c['symbol'] for c in active_symbols]

    print(f"📊 Moedas atualmente ativas: {', '.join(existing_list)}")

    for symbol in NEW_COINS:
        try:
            # Tentar obter config existente
            config_data = await db.get_coin_config(symbol)

            if config_data:
                # Apenas ativar se já existe
                await db.client.table('coins_mrrobot').update({'is_active': True}).eq('symbol', symbol).execute()
                print(f"✅ {symbol} reativado.")
            else:
                # Criar novo registro
                new_data = {
                    'symbol': symbol,
                    'is_active': True,
                    'leverage': 5,
                    'position_size_percent': 0.20
                }
                await db.client.table('coins_mrrobot').insert(new_data).execute()
                print(f"✨ {symbol} adicionado e ativado.")
        except Exception as e:
            print(f"❌ Erro ao processar {symbol}: {e}")

    # Manter BTC, ETH e BNB ativos também
    base_coins = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    for symbol in base_coins:
        await db.client.table('coins_mrrobot').update({'is_active': True}).eq('symbol', symbol).execute()

    print("\n🏆 Lista de moedas Sniper configurada com sucesso!")

if __name__ == "__main__":
    asyncio.run(update_coins())
