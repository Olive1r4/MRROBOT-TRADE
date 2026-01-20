"""
Monitor de Trades em Tempo Real - Tick-by-Tick
Monitora posições abertas via WebSocket com latência ZERO
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set
import websockets
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OpenTrade:
    """Representa um trade aberto sendo monitorado"""
    trade_id: str
    symbol: str
    entry_price: float
    quantity: float
    leverage: int
    target_price: float
    stop_loss_price: float
    entry_time: datetime
    last_price: float = 0.0
    last_update: datetime = field(default_factory=datetime.now)
    pnl_percent: float = 0.0
    pnl_usdt: float = 0.0

    def update_pnl(self, current_price: float, trading_fee: float = 0.0004):
        """
        Calcula PnL atual do trade

        Args:
            current_price: Preço atual
            trading_fee: Taxa de trading (0.04%)
        """
        self.last_price = current_price
        self.last_update = datetime.now()

        # Calcular PnL percentual BRUTO
        pnl_percent_gross = (current_price - self.entry_price) / self.entry_price

        # Descontar fees de entrada E saída
        # Fees totais = 0.04% entrada + 0.04% saída = 0.08%
        total_fees = trading_fee * 2

        # PnL LÍQUIDO (após fees)
        self.pnl_percent = pnl_percent_gross - total_fees

        # PnL em USDT (considerando alavancagem)
        position_value = self.quantity * self.entry_price
        self.pnl_usdt = position_value * self.pnl_percent * self.leverage

    def should_take_profit(self, target_profit_net: float) -> bool:
        """Verifica se atingiu o take profit (após fees)"""
        return self.pnl_percent >= target_profit_net

    def should_stop_loss(self, stop_loss_percent: float) -> bool:
        """Verifica se atingiu o stop loss"""
        return self.pnl_percent <= -stop_loss_percent


class TradeMonitor:
    """
    Monitor de trades em tempo real via WebSocket

    CRITICAL:
    - Monitora APENAS símbolos com trades abertos
    - Recebe preço A CADA TICK (milissegundos)
    - Fecha trade INSTANTANEAMENTE quando atinge target/stop
    """

    def __init__(self, config, exchange_manager, database, telegram_notifier, risk_manager):
        self.config = config
        self.exchange = exchange_manager
        self.db = database
        self.telegram = telegram_notifier
        self.risk_manager = risk_manager

        # Trades abertos sendo monitorados
        self.open_trades: Dict[str, OpenTrade] = {}

        # WebSocket connections por símbolo
        self.websockets: Dict[str, websockets.WebSocketClientProtocol] = {}

        # Símbolos sendo monitorados
        self.monitored_symbols: Set[str] = set()

        # Reconnection attempts
        self.reconnect_attempts: Dict[str, int] = {}
        self.max_reconnect_attempts = 10

        # Flag para shutdown gracioso
        self.is_running = True

        # Flag para shutdown gracioso
        self.is_running = True

    async def start(self):
        """Inicia o monitor em background"""
        logger.info("=" * 60)
        logger.info(f"🚀 TRADE MONITOR START | TP: +{self.config.TARGET_PROFIT_NET * 100:.2f}% | SL: -{self.config.STOP_LOSS_PERCENTAGE * 100:.2f}%")
        logger.info("=" * 60)

        # Carregar trades abertos do banco ao iniciar
        await self.load_open_trades_from_db()

        # Loop principal de monitoramento
        while self.is_running:
            try:
                # Verificar se há novos trades a serem monitorados
                await self.check_for_new_trades()

                # Aguardar antes de verificar novamente
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"❌ Erro no loop principal do monitor: {e}")
                await asyncio.sleep(5)

    async def load_open_trades_from_db(self):
        """Carrega trades abertos do banco de dados ao iniciar"""
        try:
            logger.info("📥 Carregando trades abertos do banco de dados...")

            open_trades_db = await self.db.get_open_trades()

            if not open_trades_db:
                logger.info("✅ Nenhum trade aberto encontrado")
                return

            for trade_db in open_trades_db:
                # Converter para OpenTrade
                open_trade = OpenTrade(
                    trade_id=trade_db['id'],
                    symbol=trade_db['symbol'],
                    entry_price=float(trade_db['entry_price']),
                    quantity=float(trade_db['quantity']),
                    leverage=int(trade_db['leverage']),
                    target_price=float(trade_db['target_price']),
                    stop_loss_price=float(trade_db['stop_loss_price']),
                    entry_time=datetime.fromisoformat(trade_db['entry_time'].replace('Z', '+00:00'))
                )

                # Adicionar à lista de monitoramento
                await self.add_trade_to_monitor(open_trade)

            logger.info(f"✅ {len(self.open_trades)} trade(s) carregado(s) para monitoramento")

        except Exception as e:
            logger.error(f"❌ Erro ao carregar trades do banco: {e}")

    async def check_for_new_trades(self):
        """Verifica se há novos trades no banco que não estão sendo monitorados"""
        try:
            open_trades_db = await self.db.get_open_trades()

            if not open_trades_db:
                return

            for trade_db in open_trades_db:
                trade_id = trade_db['id']

                # Se já está sendo monitorado, ignorar
                if trade_id in self.open_trades:
                    continue

                # Novo trade detectado
                logger.info(f"🆕 Novo trade detectado: {trade_id}")

                open_trade = OpenTrade(
                    trade_id=trade_id,
                    symbol=trade_db['symbol'],
                    entry_price=float(trade_db['entry_price']),
                    quantity=float(trade_db['quantity']),
                    leverage=int(trade_db['leverage']),
                    target_price=float(trade_db['target_price']),
                    stop_loss_price=float(trade_db['stop_loss_price']),
                    entry_time=datetime.fromisoformat(trade_db['entry_time'].replace('Z', '+00:00'))
                )

                await self.add_trade_to_monitor(open_trade)

        except Exception as e:
            logger.error(f"❌ Erro ao verificar novos trades: {e}")

    async def add_trade_to_monitor(self, trade: OpenTrade):
        """
        Adiciona um trade à lista de monitoramento

        CRITICAL:
        - Adiciona trade ao dicionário
        - Inicia WebSocket de MINITICKER para o símbolo (se ainda não existe)
        - Começa a monitorar preço em TEMPO REAL
        """
        try:
            symbol = trade.symbol

            # Adicionar trade ao dicionário
            self.open_trades[trade.trade_id] = trade

            logger.info(f"🔭 MONITORANDO: {symbol} (ID: {trade.trade_id}) | Entrada: ${trade.entry_price:.2f} | TP: ${trade.target_price:.2f} | SL: ${trade.stop_loss_price:.2f} | Qtd: {trade.quantity:.4f}")

            # Se o símbolo já está sendo monitorado, não precisa criar novo WebSocket
            if symbol in self.monitored_symbols:
                logger.info(f"✅ {symbol} já está sendo monitorado")
                return

            # Iniciar WebSocket para o símbolo
            self.monitored_symbols.add(symbol)
            asyncio.create_task(self.monitor_symbol_websocket(symbol))

        except Exception as e:
            logger.error(f"❌ Erro ao adicionar trade ao monitor: {e}")

    async def remove_trade_from_monitor(self, trade_id: str):
        """Remove um trade da lista de monitoramento"""
        try:
            if trade_id not in self.open_trades:
                return

            trade = self.open_trades[trade_id]
            symbol = trade.symbol

            # Remover trade do dicionário
            del self.open_trades[trade_id]

            logger.info(f"✅ Trade {trade_id} removido do monitoramento")

            # Verificar se ainda há outros trades deste símbolo
            has_other_trades = any(
                t.symbol == symbol for t in self.open_trades.values()
            )

            # Se não há mais trades deste símbolo, fechar WebSocket
            if not has_other_trades and symbol in self.monitored_symbols:
                logger.info(f"📴 Nenhum trade aberto de {symbol} - Encerrando WebSocket")
                self.monitored_symbols.remove(symbol)

                # Fechar WebSocket se existir
                if symbol in self.websockets:
                    await self.websockets[symbol].close()
                    del self.websockets[symbol]

        except Exception as e:
            logger.error(f"❌ Erro ao remover trade do monitor: {e}")

    async def monitor_symbol_websocket(self, symbol: str):
        """
        Monitora um símbolo via WebSocket MiniTicker

        MiniTicker = Preço atualizado A CADA TICK (mais rápido que Kline)
        """
        ws_symbol = symbol.lower()
        self.reconnect_attempts[symbol] = 0

        while self.is_running and symbol in self.monitored_symbols:
            try:
                # URL do WebSocket MiniTicker (24hr ticker info em tempo real)
                # miniTicker = Preço mais recente + volume
                ws_url = f"wss://fstream.binance.com/ws/{ws_symbol}@miniTicker"

                logger.info(f"🔌 Conectando WebSocket MiniTicker de {symbol}...")

                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as websocket:

                    self.websockets[symbol] = websocket
                    self.reconnect_attempts[symbol] = 0

                    logger.info(f"✅ WebSocket MiniTicker de {symbol} conectado!")

                    # Loop principal de recepção de dados
                    async for message in websocket:
                        try:
                            data = json.loads(message)

                            # MiniTicker contém preço atual (c = close price)
                            if 'c' in data:
                                current_price = float(data['c'])

                                # Processar tick para todos os trades deste símbolo
                                await self.process_price_tick(symbol, current_price)

                        except json.JSONDecodeError as e:
                            logger.error(f"❌ Erro ao decodificar JSON de {symbol}: {e}")
                        except Exception as e:
                            logger.error(f"❌ Erro ao processar tick de {symbol}: {e}")

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️ WebSocket MiniTicker de {symbol} fechou: {e}")
                await self.handle_reconnection(symbol)

            except Exception as e:
                logger.error(f"❌ Erro no WebSocket MiniTicker de {symbol}: {e}")
                await self.handle_reconnection(symbol)

    async def handle_reconnection(self, symbol: str):
        """Lógica de reconnection automática"""
        self.reconnect_attempts[symbol] += 1

        if self.reconnect_attempts[symbol] > self.max_reconnect_attempts:
            logger.error(f"❌ {symbol}: Máximo de tentativas de reconnection atingido")
            logger.error(f"❌ Removendo {symbol} do monitoramento")
            self.monitored_symbols.discard(symbol)
            return

        wait_time = min(2 ** self.reconnect_attempts[symbol], 5)

        logger.warning(f"🔄 Reconnection para {symbol} em {wait_time}s...")
        await asyncio.sleep(wait_time)

    async def process_price_tick(self, symbol: str, current_price: float):
        """
        Processa um tick de preço INSTANTANEAMENTE

        CRITICAL:
        - Roda A CADA TICK (milissegundos)
        - Não espera vela fechar
        - Fecha trade IMEDIATAMENTE quando atinge target/stop
        """
        try:
            # Buscar todos os trades deste símbolo
            trades_to_check = [
                trade for trade in self.open_trades.values()
                if trade.symbol == symbol
            ]

            if not trades_to_check:
                return

            for trade in trades_to_check:
                # Atualizar PnL
                trade.update_pnl(current_price, self.config.TRADING_FEE)

                # Log a cada 10s (para não poluir)
                time_since_last = (datetime.now() - trade.last_update).total_seconds()
                if time_since_last >= 10:
                    logger.info(f"📊 {symbol}: ${current_price:.2f} | PnL: {trade.pnl_percent * 100:+.3f}% (${trade.pnl_usdt:+.2f})")

                # VERIFICAR TAKE PROFIT
                if trade.should_take_profit(self.config.TARGET_PROFIT_NET):
                    logger.info(f"🎯 TAKE PROFIT: {symbol} | Entrada: ${trade.entry_price:.2f} -> Saída: ${current_price:.2f} | PnL: {trade.pnl_percent * 100:+.2f}% (${trade.pnl_usdt:+.2f})")

                    await self.close_trade(trade, current_price, "TAKE_PROFIT")

                # VERIFICAR STOP LOSS
                elif trade.should_stop_loss(self.config.STOP_LOSS_PERCENTAGE):
                    logger.warning(f"🛑 STOP LOSS: {symbol} | Entrada: ${trade.entry_price:.2f} -> Saída: ${current_price:.2f} | PnL: {trade.pnl_percent * 100:+.2f}% (${trade.pnl_usdt:+.2f})")

                    await self.close_trade(trade, current_price, "STOP_LOSS")

        except Exception as e:
            logger.error(f"❌ Erro ao processar tick de {symbol}: {e}")

    async def close_trade(self, trade: OpenTrade, exit_price: float, exit_reason: str):
        """
        Fecha um trade IMEDIATAMENTE

        Args:
            trade: Trade a ser fechado
            exit_price: Preço de saída
            exit_reason: Motivo (TAKE_PROFIT ou STOP_LOSS)
        """
        try:
            logger.info(f"🔴 Fechando trade {trade.trade_id} ({exit_reason})...")

            # Executar ordem de VENDA no exchange
            if self.config.MODE == "PROD":
                logger.info(f"📤 Executando ordem MARKET SELL de {trade.quantity:.4f} {trade.symbol}...")

                try:
                    order = await self.exchange.place_order(
                        symbol=trade.symbol,
                        side='SELL',
                        order_type='MARKET',
                        quantity=trade.quantity,
                        leverage=trade.leverage
                    )

                    logger.info(f"✅ Ordem de venda executada: {order.get('id')}")

                except Exception as e:
                    logger.error(f"❌ Erro ao executar ordem de venda: {e}")
                    # Continuar mesmo se falhar (registrar no DB)

            else:
                logger.info(f"🔵 MOCK MODE: Simulando venda de {trade.quantity:.4f} {trade.symbol}")

            # Atualizar trade no banco de dados
            await self.db.update_trade_exit(
                trade_id=trade.trade_id,
                exit_price=exit_price,
                exit_reason=exit_reason,
                pnl_percent=trade.pnl_percent,
                pnl_usdt=trade.pnl_usdt
            )

            # Atualizar PnL diário
            await self.db.update_daily_pnl(datetime.now().date(), trade.pnl_usdt)

            # Definir cooldown para o símbolo
            await self.risk_manager.set_trade_cooldown(trade.symbol)

            # Notificar via Telegram
            await self.telegram.notify_sell_order(
                {
                    'symbol': trade.symbol,
                    'entry_price': trade.entry_price,
                    'exit_price': exit_price,
                    'quantity': trade.quantity,
                    'leverage': trade.leverage,
                    'pnl_percent': trade.pnl_percent,
                    'pnl_usdt': trade.pnl_usdt,
                    'exit_reason': exit_reason,
                    'duration_seconds': (datetime.now() - trade.entry_time).total_seconds()
                },
                self.config
            )

            # Remover do monitoramento
            await self.remove_trade_from_monitor(trade.trade_id)

            logger.info(f"✅ Trade {trade.trade_id} fechado com sucesso!")

        except Exception as e:
            logger.error(f"❌ Erro ao fechar trade: {e}")

    async def shutdown(self):
        """Encerra o monitor graciosamente"""
        logger.info("🛑 Encerrando TradeMonitor...")
        self.is_running = False

        # Fechar todos os WebSockets
        for symbol, ws in self.websockets.items():
            try:
                await ws.close()
                logger.info(f"✅ WebSocket de {symbol} fechado")
            except Exception as e:
                logger.error(f"❌ Erro ao fechar WebSocket de {symbol}: {e}")

        logger.info("✅ TradeMonitor encerrado")


async def start_trade_monitor(config, exchange_manager, database, telegram_notifier, risk_manager):
    """Função auxiliar para iniciar o monitor"""
    monitor = TradeMonitor(config, exchange_manager, database, telegram_notifier, risk_manager)
    await monitor.start()
