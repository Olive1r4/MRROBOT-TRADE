"""
Bot de Scalping para Binance Futures
Aplicação principal com webhook FastAPI
"""
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import logging
import asyncio
from datetime import datetime
import uvicorn

from src.config import get_config
from src.exchange_manager import ExchangeManager
from src.indicators import SignalAnalyzer
from src.risk_manager import RiskManager
from src.database import Database
from src.telegram_notifier import TelegramNotifier

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/scalping_bot.log'),
        logging.StreamHandler()
    ]
)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Silenciar logs do httpx (Supabase e outros requests)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Inicializar aplicação
app = FastAPI(
    title="Scalping Bot API",
    description="Bot de Scalping para Binance Futures com análise técnica avançada",
    version="1.0.0"
)

# Carregar configurações
config = get_config()

# Inicializar componentes
db = Database(config)
exchange = ExchangeManager(config)
signal_analyzer = SignalAnalyzer(config)
risk_manager = RiskManager(config, db)
telegram = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)

logger.info(f"🤖 SCALPING BOT | Mode: {config.MODE} | Target: {config.TARGET_PROFIT * 100:.2f}% | TF: {config.TIMEFRAME} | SL: {config.DAILY_STOP_LOSS * 100:.1f}%")


# ============================================
# MODELOS DE DADOS
# ============================================

class WebhookSignal(BaseModel):
    """Modelo para sinal do webhook"""
    symbol: str
    action: str  # 'buy' ou 'sell' (para scalping, usamos apenas 'buy')
    price: Optional[float] = None
    timestamp: Optional[str] = None


class ManualTrade(BaseModel):
    """Modelo para trade manual"""
    symbol: str
    usdt_amount: Optional[float] = None


# ============================================
# EVENTOS DO FASTAPI
# ============================================

@app.on_event("startup")
async def startup_event():
    """Evento executado quando o servidor inicia"""
    try:
        # Enviar notificação de startup
        await telegram.notify_startup(config)

        # Iniciar MARKET SCANNER em background (detecta entradas tick-by-tick)
        if config.ENABLE_SCANNER:
            from src.market_scanner import start_market_scanner
            asyncio.create_task(start_market_scanner(config, exchange, risk_manager, db, telegram))
            logger.info("🔍 Market Scanner iniciado (Entrada Tempo Real)")

        # Iniciar TRADE MONITOR em background (monitora saídas tick-by-tick)
        from src.trade_monitor import start_trade_monitor
        asyncio.create_task(start_trade_monitor(config, exchange, db, telegram, risk_manager))
        logger.info("🔭 Trade Monitor iniciado (Saída Tempo Real)")
    except Exception as e:
        logger.error(f"⚠️ Erro ao enviar notificação de startup: {e}")


# ============================================
# FUNÇÕES AUXILIARES
# ============================================

async def execute_trade(
    symbol: str,
    webhook_price: Optional[float] = None,
    # Parâmetros do scanner (pré-validados)
    scanner_validated: bool = False,
    scanner_price: Optional[float] = None,
    scanner_indicators: Optional[dict] = None
):
    """
    Executa um trade completo com todas as validações

    Args:
        symbol: Símbolo da moeda (ex: BTCUSDT)
        webhook_price: Preço sugerido pelo webhook (opcional)
        scanner_validated: Se True, pula validação de sinal (já validado pelo scanner)
        scanner_price: Preço detectado pelo scanner
        scanner_indicators: Indicadores pré-calculados pelo scanner
    """
    try:
        logger.info(f"🚀 INICIANDO TRADE: {symbol}")

        # 1. VALIDAÇÕES DE RISCO
        validation = await risk_manager.validate_trade_entry(symbol)

        if not validation['allowed']:
            logger.warning(f"❌ Trade bloqueado para {symbol}")
            for reason in validation['reasons']:
                logger.warning(f"   {reason}")

            await db.log('WARNING', f'Trade bloqueado: {symbol}', {
                'reasons': validation['reasons']
            }, symbol=symbol)

            return {
                'success': False,
                'message': 'Trade bloqueado por guardrails de segurança',
                'reasons': validation['reasons']
            }

        coin_config = validation['coin_config']

        # 2. OBTER DADOS DO MERCADO (ou usar do scanner)
        if scanner_validated and scanner_price and scanner_indicators:
            # Usar dados já validados pelo scanner
            logger.info(f"📊 Usando dados pré-validados do scanner")
            current_price = scanner_price
            signal = {
                'should_enter': True,
                'reason': 'Scanner: RSI oversold + BB lower + EMA uptrend',
                'take_profit': scanner_indicators['take_profit'],
                'stop_loss': scanner_indicators['stop_loss'],
                'indicators': scanner_indicators
            }
            logger.info(f"💰 Preço: ${current_price:.4f} | RSI: {scanner_indicators['rsi']:.2f} | BB: ${scanner_indicators['bb_lower']:.2f} | EMA: ${scanner_indicators['ema_200']:.2f}")
        else:
            # Buscar dados normalmente (webhook ou manual)
            logger.info(f"📊 Obtendo dados de mercado de {symbol}...")

            current_price = exchange.get_current_price(symbol)
            ohlcv_data = exchange.fetch_ohlcv(symbol, config.TIMEFRAME, limit=500)

            logger.info(f"💰 Preço atual: ${current_price:.4f}")

            # 3. ANÁLISE TÉCNICA
            logger.info(f"📈 Analisando indicadores técnicos...")

            signal = signal_analyzer.analyze_entry_signal(symbol, ohlcv_data, current_price)

            if not signal['should_enter']:
                logger.info(f"⏸️ Sinal de entrada NÃO confirmado para {symbol}")
                logger.info(f"   Razão: {signal['reason']}")

                await db.log('INFO', f'Sinal de entrada negado: {symbol}', {
                    'reason': signal['reason'],
                    'indicators': signal['indicators']
                }, symbol=symbol)

                return {
                    'success': False,
                    'message': 'Sinal de entrada não confirmado',
                    'reason': signal['reason'],
                    'indicators': signal['indicators']
                }

        logger.info(f"✅ Sinal de entrada CONFIRMADO!")

        # 4. CALCULAR TAMANHO DA POSIÇÃO
        usdt_amount, leverage = await risk_manager.calculate_position_size(
            symbol, current_price, coin_config
        )

        # 5. PREPARAR ORDEM
        quantity, total_value = exchange.calculate_order_size(symbol, usdt_amount, current_price)

        logger.info(f"💼 Preparando ordem: {quantity} {symbol} (${total_value:.2f}) | {leverage}x | TP: ${signal['take_profit']:.4f} | SL: ${signal['stop_loss']:.4f}")

        # 6. CONFIGURAR EXCHANGE
        exchange.set_leverage(symbol, leverage)
        exchange.set_margin_mode(symbol, 'isolated')

        # 7. EXECUTAR ORDEM DE ENTRADA
        logger.info(f"🔄 Executando ordem de compra...")

        order_entry = exchange.create_market_buy_order(symbol, quantity, current_price)

        # Registrar no rate limiter
        risk_manager.register_order()

        # 8. SALVAR NO BANCO DE DADOS
        trade_data = {
            'symbol': symbol,
            'side': 'buy',
            'entry_price': current_price,
            'quantity': quantity,
            'leverage': leverage,
            'stop_loss_price': signal['stop_loss'],
            'status': 'open'
        }

        trade_id = await db.create_trade(trade_data)

        logger.info(f"✅ Trade criado com ID: {trade_id}")

        await db.log('INFO', f'Trade aberto: {symbol}', {
            'trade_id': trade_id,
            'entry_price': current_price,
            'quantity': quantity,
            'indicators': signal['indicators']
        }, symbol=symbol, trade_id=trade_id)

        # Notificar abertura via Telegram
        await telegram.notify_trade_open(trade_data, signal)

        logger.info(f"✅ TRADE EXECUTADO COM SUCESSO! ID: {trade_id}")

        # 9. MONITORAR TRADE (em background)
        asyncio.create_task(monitor_trade(trade_id))

        return {
            'success': True,
            'message': 'Trade executado com sucesso',
            'trade_id': trade_id,
            'symbol': symbol,
            'entry_price': current_price,
            'quantity': quantity,
            'target_price': signal['take_profit'],
            'stop_loss': signal['stop_loss'],
            'indicators': signal['indicators']
        }

    except Exception as e:
        logger.error(f"❌ Erro ao executar trade: {str(e)}", exc_info=True)

        await db.log('ERROR', f'Erro ao executar trade: {symbol}', {
            'error': str(e)
        }, symbol=symbol)

        return {
            'success': False,
            'message': f'Erro ao executar trade: {str(e)}'
        }


async def monitor_trade(trade_id: int):
    """
    Monitora um trade aberto e fecha quando atingir TP ou SL

    Args:
        trade_id: ID do trade a ser monitorado
    """
    try:
        logger.info(f"👁️ Monitorando trade {trade_id}...")

        while True:
            # Aguardar intervalo (verifica a cada 5 segundos)
            await asyncio.sleep(5)

            # Obter dados do trade
            trade = await db.get_trade_by_id(trade_id)

            if not trade or trade['status'] != 'open':
                logger.info(f"✋ Trade {trade_id} não está mais aberto. Parando monitoramento.")
                break

            symbol = trade['symbol']
            entry_price = float(trade['entry_price'])
            quantity = float(trade['quantity'])
            target_price = float(trade['target_price'])
            stop_loss = float(trade['stop_loss_price'])

            # Obter preço atual
            current_price = exchange.get_current_price(symbol)

            # Verificar condições de saída
            should_exit, exit_reason = signal_analyzer.check_exit_conditions(
                entry_price, current_price, stop_loss, target_price
            )

            if should_exit:
                logger.info(f"🚪 Condição de saída atingida para trade {trade_id}")
                logger.info(f"   Razão: {exit_reason}")

                # Executar ordem de venda
                order_exit = exchange.create_market_sell_order(symbol, quantity, current_price)

                # Registrar no rate limiter
                risk_manager.register_order()

                # Fechar trade no banco
                pnl, pnl_pct = await db.close_trade(
                    trade_id,
                    current_price,
                    exit_reason,
                    order_exit.get('id')
                )

                # Definir cooldown
                await risk_manager.set_trade_cooldown(symbol)

                logger.info(f"✅ Trade {trade_id} fechado")
                logger.info(f"   PnL: ${pnl:.2f} ({pnl_pct:+.2f}%)")

                await db.log('INFO', f'Trade fechado: {symbol}', {
                    'trade_id': trade_id,
                    'exit_price': current_price,
                    'pnl': pnl,
                    'pnl_percentage': pnl_pct,
                    'reason': exit_reason
                }, symbol=symbol, trade_id=trade_id)

                # Notificar fechamento via Telegram
                await telegram.notify_trade_close(trade, current_price, pnl, pnl_pct)

                break

    except Exception as e:
        logger.error(f"❌ Erro ao monitorar trade {trade_id}: {str(e)}", exc_info=True)

        await db.log('ERROR', f'Erro ao monitorar trade', {
            'trade_id': trade_id,
            'error': str(e)
        }, trade_id=trade_id)


# ============================================
# ENDPOINTS DA API
# ============================================

@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        'name': 'Scalping Bot API',
        'version': '1.0.0',
        'status': 'online',
        'mode': config.MODE,
        'timestamp': datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """Verifica a saúde da aplicação"""
    try:
        # Testar conexão com exchange
        exchange_ok = exchange.is_market_open('BTCUSDT')

        # Obter estatísticas
        stats = await db.get_statistics(days=1)

        # Verificar circuit breaker
        daily_pnl = await db.get_daily_pnl()
        circuit_breaker_active = daily_pnl.get('is_circuit_breaker_active', False) if daily_pnl else False

        return {
            'status': 'healthy',
            'mode': config.MODE,
            'exchange_connected': exchange_ok,
            'circuit_breaker_active': circuit_breaker_active,
            'today_stats': {
                'total_pnl': stats.get('total_pnl', 0),
                'total_trades': stats.get('total_trades', 0),
                'win_rate': stats.get('win_rate', 0)
            },
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
        )


@app.post("/webhook")
async def webhook(
    signal: WebhookSignal,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(None)
):
    """
    Endpoint principal do webhook para receber sinais

    Headers:
        x-webhook-secret: Token secreto para autenticação

    Body:
        {
            "symbol": "BTCUSDT",
            "action": "buy",
            "price": 50000.00,
            "timestamp": "2024-01-01T12:00:00Z"
        }
    """
    try:
        # Validar token de segurança
        if x_webhook_secret != config.WEBHOOK_SECRET:
            logger.warning(f"⚠️ Tentativa de acesso não autorizado ao webhook")
            raise HTTPException(status_code=401, detail="Token inválido")

        logger.info(f"📥 Webhook recebido: {signal.symbol} - {signal.action}")

        # Validar ação (apenas buy para scalping long)
        if signal.action.lower() != 'buy':
            return {
                'success': False,
                'message': f'Ação {signal.action} não suportada (apenas buy para scalping long)'
            }

        # Executar trade em background
        background_tasks.add_task(execute_trade, signal.symbol, signal.price)

        return {
            'success': True,
            'message': 'Sinal recebido e processamento iniciado',
            'symbol': signal.symbol,
            'action': signal.action,
            'received_at': datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao processar webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trade/manual")
async def manual_trade(trade: ManualTrade, background_tasks: BackgroundTasks):
    """
    Endpoint para executar trade manual

    Body:
        {
            "symbol": "BTCUSDT",
            "usdt_amount": 100.00
        }
    """
    try:
        logger.info(f"👤 Trade manual solicitado: {trade.symbol}")

        # Executar trade em background
        background_tasks.add_task(execute_trade, trade.symbol)

        return {
            'success': True,
            'message': 'Trade manual iniciado',
            'symbol': trade.symbol
        }

    except Exception as e:
        logger.error(f"❌ Erro ao executar trade manual: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trades/open")
async def get_open_trades():
    """Retorna todos os trades abertos"""
    try:
        trades = await db.get_open_trades()
        return {
            'success': True,
            'count': len(trades),
            'trades': trades
        }
    except Exception as e:
        logger.error(f"❌ Erro ao obter trades abertos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trades/{trade_id}")
async def get_trade(trade_id: int):
    """Retorna informações de um trade específico"""
    try:
        trade = await db.get_trade_by_id(trade_id)

        if not trade:
            raise HTTPException(status_code=404, detail="Trade não encontrado")

        return {
            'success': True,
            'trade': trade
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao obter trade: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trades/{trade_id}/close")
async def close_trade_manually(trade_id: int):
    """Fecha um trade manualmente"""
    try:
        trade = await db.get_trade_by_id(trade_id)

        if not trade:
            raise HTTPException(status_code=404, detail="Trade não encontrado")

        if trade['status'] != 'open':
            raise HTTPException(status_code=400, detail="Trade não está aberto")

        symbol = trade['symbol']
        quantity = float(trade['quantity'])

        # Obter preço atual e executar venda
        current_price = exchange.get_current_price(symbol)
        order_exit = exchange.create_market_sell_order(symbol, quantity, current_price)

        # Fechar no banco
        pnl, pnl_pct = await db.close_trade(
            trade_id,
            current_price,
            "Fechamento manual",
            order_exit.get('id')
        )

        await risk_manager.set_trade_cooldown(symbol)

        logger.info(f"✅ Trade {trade_id} fechado manualmente")

        return {
            'success': True,
            'message': 'Trade fechado com sucesso',
            'trade_id': trade_id,
            'exit_price': current_price,
            'pnl': pnl,
            'pnl_percentage': pnl_pct
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao fechar trade: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_statistics(days: int = 30):
    """Retorna estatísticas dos últimos N dias"""
    try:
        stats = await db.get_statistics(days)
        return {
            'success': True,
            'period_days': days,
            'statistics': stats
        }
    except Exception as e:
        logger.error(f"❌ Erro ao obter estatísticas: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config/coins")
async def get_coins_config():
    """Retorna configuração de todas as moedas"""
    try:
        coins = await db.get_active_coins()
        return {
            'success': True,
            'count': len(coins),
            'coins': coins
        }
    except Exception as e:
        logger.error(f"❌ Erro ao obter configuração das moedas: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/config/coins/{symbol}/toggle")
async def toggle_coin_status(symbol: str):
    """Ativa/desativa uma moeda"""
    try:
        coin_config = await db.get_coin_config(symbol)

        if not coin_config:
            raise HTTPException(status_code=404, detail="Moeda não encontrada")

        new_status = not coin_config['is_active']
        await db.update_coin_status(symbol, new_status)

        return {
            'success': True,
            'message': f'Moeda {symbol} {"ativada" if new_status else "desativada"}',
            'symbol': symbol,
            'is_active': new_status
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao alterar status da moeda: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# INICIALIZAÇÃO
# ============================================

if __name__ == "__main__":
    # Criar diretório de logs se não existir
    import os
    os.makedirs('logs', exist_ok=True)

    # Iniciar servidor
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=config.WEBHOOK_PORT,
        reload=False,
        log_level="info"
    )
