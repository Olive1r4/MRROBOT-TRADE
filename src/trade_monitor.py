"""
Monitor de Trades em Tempo Real - Tick-by-Tick
Monitora posições abertas via WebSocket com latência ZERO
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
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
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pnl_percent: float = 0.0
    pnl_usdt: float = 0.0
    mode: str = "MOCK"
    is_closing: bool = False

    def update_pnl(self, current_price: float, trading_fee: float = 0.0004):
        """
        Calcula PnL atual do trade

        Args:
            current_price: Preço atual
            trading_fee: Taxa de trading (0.04%)
        """
        self.last_price = current_price
        self.last_update = datetime.now(timezone.utc)

        # Calcular PnL percentual BRUTO
        pnl_percent_gross = (current_price - self.entry_price) / self.entry_price

        # Descontar fees de entrada E saída
        # Fees totais = 0.04% entrada + 0.04% saída = 0.08%
        total_fees = trading_fee * 2

        # PnL LÍQUIDO (após fees)
        self.pnl_percent = pnl_percent_gross - total_fees

        # PnL em USDT
        # position_value já contempla o tamanho total da posição
        position_value = self.quantity * self.entry_price
        self.pnl_usdt = position_value * self.pnl_percent

    def should_take_profit(self, target_profit_net: float) -> bool:
        """
        Verifica se atingiu o take profit (após fees)
        Prioriza o target_price dinâmico se estiver definido.
        """
        if self.target_price > 0 and self.last_price >= self.target_price:
            return True
        return self.pnl_percent >= target_profit_net

    def should_stop_loss(self, stop_loss_percent: float) -> bool:
        """
        Verifica se atingiu o stop loss
        Prioriza o stop_loss_price dinâmico se estiver definido.
        """
        if self.stop_loss_price > 0 and self.last_price <= self.stop_loss_price:
            return True
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
        self.trades_lock = asyncio.Lock()

        # Flag para shutdown gracioso
        self.is_running = True

        # Conexão WebSocket centralizada (Multi-Stream)
        self.ws_main: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_lock = asyncio.Lock()
        self.subscribed_streams: Set[str] = set()

        # Task única para gerenciar o WebSocket
        self.monitor_task: Optional[asyncio.Task] = None

        # Controle de log a cada 10s por trade
        self.last_log_time: Dict[str, datetime] = {}

        # Flag para shutdown gracioso
        self.is_running = True

    async def start(self):
        """Inicia o monitor em background"""
        logger.info("=" * 60)
        logger.info(f"🚀 TRADE MONITOR START | TP: +{self.config.TARGET_PROFIT_NET * 100:.2f}% | SL: -{self.config.STOP_LOSS_PERCENTAGE * 100:.2f}%")
        logger.info("=" * 60)

        # Carregar trades abertos do banco ao iniciar
        await self.load_open_trades_from_db()

        # Iniciar conexão WebSocket Multi-Stream em background
        self.monitor_task = asyncio.create_task(self.monitor_multi_stream())

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

            open_trades_db = self.db.get_open_trades()

            if not open_trades_db:
                logger.info("✅ Nenhum trade aberto encontrado")
                return

            for trade_db in open_trades_db:
                # Tratar string de tempo (Supabase pode enviar mais de 6 casas decimais)
                entry_time_str = self._fix_isoformat(trade_db.get('entry_time', datetime.now(timezone.utc).isoformat()))

                # Converter para OpenTrade com segurança
                open_trade = OpenTrade(
                    trade_id=trade_db.get('id'),
                    symbol=trade_db.get('symbol'),
                    entry_price=float(trade_db.get('entry_price') or 0),
                    quantity=float(trade_db.get('quantity') or 0),
                    leverage=int(trade_db.get('leverage') or 1),
                    target_price=float(trade_db.get('target_price') or 0),
                    stop_loss_price=float(trade_db.get('stop_loss_price') or 0),
                    entry_time=datetime.fromisoformat(entry_time_str.replace('Z', '+00:00')),
                    mode=trade_db.get('mode', 'MOCK')
                )

                # Adicionar à lista de monitoramento
                await self.add_trade_to_monitor(open_trade)

            logger.info(f"✅ {len(self.open_trades)} trade(s) carregado(s) para monitoramento")

        except Exception as e:
            logger.error(f"❌ Erro ao carregar trades do banco: {e}")

    async def check_for_new_trades(self):
        """Verifica se há novos trades no banco que não estão sendo monitorados"""
        try:
            open_trades_db = self.db.get_open_trades()

            if not open_trades_db:
                return

            for trade_db in open_trades_db:
                trade_id = trade_db['id']

                # Se já está sendo monitorado, ignorar
                if trade_id in self.open_trades:
                    continue

                # Novo trade detectado
                logger.info(f"🆕 Novo trade detectado: {trade_id}")

                # Tratar string de tempo (Supabase pode enviar mais de 6 casas decimais)
                entry_time_str = self._fix_isoformat(trade_db.get('entry_time', datetime.now(timezone.utc).isoformat()))

                open_trade = OpenTrade(
                    trade_id=trade_id,
                    symbol=trade_db.get('symbol'),
                    entry_price=float(trade_db.get('entry_price') or 0),
                    quantity=float(trade_db.get('quantity') or 0),
                    leverage=int(trade_db.get('leverage') or 1),
                    target_price=float(trade_db.get('target_price') or 0),
                    stop_loss_price=float(trade_db.get('stop_loss_price') or 0),
                    entry_time=datetime.fromisoformat(entry_time_str.replace('Z', '+00:00')),
                    mode=trade_db.get('mode', 'MOCK')
                )

                await self.add_trade_to_monitor(open_trade)

        except Exception as e:
            logger.error(f"❌ Erro ao verificar novos trades: {e}")

    def _fix_isoformat(self, timestamp_str: str) -> str:
        """
        Helper para garantir que a string ISO tenha precision compatível com Python 3.10
        Python 3.10 exige 3 ou 6 dígitos nos microssegundos se houver ponto decimal.
        """
        if not timestamp_str or not isinstance(timestamp_str, str):
            return timestamp_str

        if '.' not in timestamp_str:
            return timestamp_str

        try:
            # Separar a parte das frações e o resto (timezone)
            # Ex: 2024-01-01T12:00:00.12345+00:00 -> parts=['2024-01-01T12:00:00', '12345+00:00']
            main_part, sub_part = timestamp_str.split('.', 1)

            # Encontrar onde termina a fração e começa o offset (Z, + ou -)
            offset_idx = -1
            for i, char in enumerate(sub_part):
                if char in ('Z', '+', '-'):
                    offset_idx = i
                    break

            if offset_idx == -1:
                fraction = sub_part
                offset = ""
            else:
                fraction = sub_part[:offset_idx]
                offset = sub_part[offset_idx:]

            # Ajustar fração para 6 dígitos (Python 3.10 standard)
            if len(fraction) > 6:
                fraction = fraction[:6]
            elif len(fraction) < 6:
                fraction = fraction.ljust(6, '0')

            return f"{main_part}.{fraction}{offset}"
        except Exception as e:
            logger.error(f"⚠️ Erro ao corrigir timestamp {timestamp_str}: {e}")
            return timestamp_str

    async def add_trade_to_monitor(self, trade: OpenTrade):
        """
        Adiciona um trade à lista de monitoramento e assina o stream no WebSocket
        """
        try:
            symbol = trade.symbol
            async with self.trades_lock:
                self.open_trades[trade.trade_id] = trade

            logger.info(f"🔭 MONITORANDO: {symbol} (ID: {trade.trade_id}) | Entrada: ${trade.entry_price:.2f} | TP: ${trade.target_price:.2f} | SL: ${trade.stop_loss_price:.2f} | Qtd: {trade.quantity:.4f}")

            # Assinar stream para este símbolo
            await self.subscribe_symbol(symbol)

        except Exception as e:
            logger.error(f"❌ Erro ao adicionar trade ao monitor: {e}")

    async def subscribe_symbol(self, symbol: str):
        """Assina o miniTicker do símbolo na conexão existente"""
        try:
            stream = f"{symbol.lower()}@miniTicker"

            async with self.ws_lock:
                if stream in self.subscribed_streams:
                    return

                if self.ws_main and not getattr(self.ws_main, 'closed', True):
                    msg = {
                        "method": "SUBSCRIBE",
                        "params": [stream],
                        "id": int(datetime.now().timestamp())
                    }
                    await self.ws_main.send(json.dumps(msg))
                    self.subscribed_streams.add(stream)
                    logger.info(f"📡 Inscrito em stream de monitoramento: {stream}")
                else:
                    logger.debug(f"⏳ Aguardando conexão para inscrever trade de {symbol}")

        except Exception as e:
            logger.error(f"❌ Erro ao inscrever stream para {symbol}: {e}")

    async def remove_trade_from_monitor(self, trade_id: str):
        """Remove um trade e cancela assinatura se não houver outros para o símbolo"""
        try:
            if trade_id not in self.open_trades:
                return

            async with self.trades_lock:
                if trade_id not in self.open_trades:
                    return
                trade = self.open_trades[trade_id]
                symbol = trade.symbol
                del self.open_trades[trade_id]

            logger.info(f"✅ Trade {trade_id} removido do monitoramento")

            # Verificar se ainda há outros trades deste símbolo
            has_other_trades = any(t.symbol == symbol for t in self.open_trades.values())

            if not has_other_trades:
                await self.unsubscribe_symbol(symbol)

        except Exception as e:
            logger.error(f"❌ Erro ao remover trade do monitor: {e}")

    async def unsubscribe_symbol(self, symbol: str):
        """Cancela assinatura do miniTicker para economizar recursos"""
        try:
            stream = f"{symbol.lower()}@miniTicker"

            async with self.ws_lock:
                if stream not in self.subscribed_streams:
                    return

                if self.ws_main and not getattr(self.ws_main, 'closed', True):
                    msg = {
                        "method": "UNSUBSCRIBE",
                        "params": [stream],
                        "id": int(datetime.now().timestamp())
                    }
                    await self.ws_main.send(json.dumps(msg))
                    self.subscribed_streams.remove(stream)
                    logger.info(f"📴 Cancelada assinatura de stream: {stream}")

        except Exception as e:
            logger.error(f"❌ Erro ao cancelar stream para {symbol}: {e}")

    async def monitor_multi_stream(self):
        """Mantém conexão centralizada para monitorar trades abertos"""
        reconnect_attempts = 0

        while self.is_running:
            try:
                base_url = "wss://fstream.binance.com/stream"
                logger.info("🔌 Conectando WebSocket Multi-Stream de Monitoramento...")

                async with websockets.connect(
                    base_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as websocket:

                    self.ws_main = websocket
                    reconnect_attempts = 0

                    # Assinar símbolos que já estão em monitoramento (em caso de reconexão)
                    symbols_to_sub = set(t.symbol for t in self.open_trades.values())
                    if symbols_to_sub:
                        streams = [f"{s.lower()}@miniTicker" for s in symbols_to_sub]
                        msg = {
                            "method": "SUBSCRIBE",
                            "params": streams,
                            "id": int(datetime.now().timestamp())
                        }
                        await websocket.send(json.dumps(msg))
                        self.subscribed_streams.update(streams)
                        logger.info(f"✅ Reconectado e assinado em {len(streams)} streams de monitoramento")

                    logger.info("✅ Trade Monitor WebSocket conectado!")

                    async for message in websocket:
                        try:
                            data = json.loads(message)

                            if "stream" in data and "data" in data:
                                payload = data["data"]
                                if 'c' in payload:
                                    symbol = payload["s"] # 's' é o símbolo no ticker da Binance
                                    current_price = float(payload['c'])
                                    await self.process_price_tick(symbol, current_price)

                        except Exception as e:
                            logger.error(f"❌ Erro ao processar ticker no monitor: {e}")

            except Exception as e:
                self.ws_main = None
                reconnect_attempts += 1
                wait_time = min(2 ** reconnect_attempts, 30)
                logger.warning(f"⚠️ Erro no TradeMonitor WebSocket: {e}. Reconectando em {wait_time}s...")
                await asyncio.sleep(wait_time)

    async def process_price_tick(self, symbol: str, current_price: float):
        """
        Processa um tick de preço INSTANTANEAMENTE
        """
        try:
            trades_to_close = []

            async with self.trades_lock:
                # Buscar todos os trades deste símbolo
                trades_to_check = [
                    trade for trade in self.open_trades.values()
                    if trade.symbol == symbol and not trade.is_closing
                ]

                if not trades_to_check:
                    return

                now = datetime.now(timezone.utc)

                for trade in trades_to_check:
                    # Atualizar PnL
                    trade.update_pnl(current_price, self.config.TRADING_FEE)

                    # Log a cada 10s
                    last_log = self.last_log_time.get(trade.trade_id, datetime.min.replace(tzinfo=timezone.utc))
                    if (now - last_log).total_seconds() >= 10:
                        self.last_log_time[trade.trade_id] = now
                        logger.info(f"📊 {symbol}: ${current_price:.4f} | PnL: {trade.pnl_percent * 100:+.3f}% (Target: ${trade.target_price:.4f})")

                    # VERIFICAR TIME-EXIT (45 minutos)
                    duration_minutes = (now - trade.entry_time).total_seconds() / 60
                    if duration_minutes >= 45:
                        if abs(trade.pnl_percent) <= 0.001:
                            logger.info(f"⏳ TIME-EXIT TRIGGER: {symbol} atingiu {duration_minutes:.1f} min com PnL neutro ({trade.pnl_percent*100:+.2f}%).")
                            trade.is_closing = True
                            trades_to_close.append((trade, "TIME_EXIT"))
                            continue

                    # VERIFICAR TAKE PROFIT
                    if trade.should_take_profit(self.config.TARGET_PROFIT_NET):
                        logger.info(f"🎯 TAKE PROFIT TRIGGER: {symbol} | PnL: {trade.pnl_percent * 100:+.2f}% (ID: {trade.trade_id})")
                        trade.is_closing = True
                        trades_to_close.append((trade, "TAKE_PROFIT"))

                    # VERIFICAR STOP LOSS
                    elif trade.should_stop_loss(self.config.STOP_LOSS_PERCENTAGE):
                        logger.warning(f"🛑 STOP LOSS TRIGGER: {symbol} | PnL: {trade.pnl_percent * 100:+.2f}% (ID: {trade.trade_id})")
                        trade.is_closing = True
                        trades_to_close.append((trade, "STOP_LOSS"))

            # EXECUTAR FECHAMENTOS FORA DO LOCK
            for trade, reason in trades_to_close:
                # Criar task para não bloquear o loop de ticks
                asyncio.create_task(self.close_trade(trade, current_price, reason))

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
            self.db.update_trade_exit(
                trade_id=trade.trade_id,
                exit_price=exit_price,
                exit_reason=exit_reason,
                pnl_percent=trade.pnl_percent,
                pnl_usdt=trade.pnl_usdt
            )

            # Atualizar PnL diário
            self.db.update_daily_pnl(datetime.now(timezone.utc).date(), trade.pnl_usdt)

            # Definir cooldown para o símbolo
            self.risk_manager.set_trade_cooldown(trade.symbol)

            # Notificar via Telegram
            await self.telegram.notify_trade_close(
                {
                    'symbol': trade.symbol,
                    'entry_price': trade.entry_price,
                    'quantity': trade.quantity,
                    'leverage': trade.leverage,
                    'mode': trade.mode,
                    'entry_time': trade.entry_time
                },
                exit_price=exit_price,
                pnl=trade.pnl_usdt,
                pnl_percentage=trade.pnl_percent * 100
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

        if self.ws_main:
            try:
                await self.ws_main.close()
                logger.info("✅ WebSocket centralizado fechado")
            except Exception as e:
                logger.error(f"❌ Erro ao fechar WebSocket: {e}")

        logger.info("✅ TradeMonitor encerrado")


async def start_trade_monitor(config, exchange_manager, database, telegram_notifier, risk_manager):
    """Função auxiliar para iniciar o monitor"""
    monitor = TradeMonitor(config, exchange_manager, database, telegram_notifier, risk_manager)
    await monitor.start()
