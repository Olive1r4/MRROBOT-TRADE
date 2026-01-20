
import asyncio
import os
import sys
from datetime import datetime

# Adicionar o diretório raiz ao path para importar src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.database import Database

async def clear_data():
    print("🧹 Iniciando limpeza completa de dados de trade...")
    config = Config()
    db = Database(config)

    force = "--force" in sys.argv

    if not force:
        confirm = input("⚠️ Isso apagará TODOS os trades, logs e estatísticas. Digite 'sim' para confirmar: ")
        if confirm.lower() != 'sim':
            print("❌ Operação cancelada.")
            return

    try:
        # 1. Limpar logs
        print("📝 Limpando logs...")
        db.client.table('logs_mrrobot').delete().neq('id', -1).execute()

        # 2. Limpar trades
        print("📈 Limpando histórico de trades...")
        db.client.table('trades_mrrobot').delete().neq('id', -1).execute()

        # 3. Limpar estatísticas diárias
        print("📊 Limpando estatísticas diárias...")
        db.client.table('daily_stats_mrrobot').delete().neq('trade_date', '1970-01-01').execute()

        # 4. Limpar cooldowns
        print("⏱️ Limpando cooldowns ativos...")
        db.client.table('cooldown_mrrobot').delete().neq('symbol', '').execute()

        print("\n✨ BANCO DE DADOS LIMPO COM SUCESSO!")
        print("O bot agora iniciará como se fosse a primeira execução.")

    except Exception as e:
        print(f"❌ Erro durante a limpeza: {e}")

if __name__ == "__main__":
    asyncio.run(clear_data())
