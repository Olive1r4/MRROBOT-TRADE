"""
Market Scanner com Monitoramento Tick-by-Tick para ENTRADA
Atualiza indicadores a cada 1 minuto (vela fechada)
Verifica condições de entrada A CADA TICK (tempo real)
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from collections import deque
from dataclasses import dataclass
import websockets

logger = logging.getLogger(__name__)


@dataclass
class MarketState:
    """Estado dos indicadores e preço de um símbolo"""
    symbol: str
    last_update: datetime
    current_price: float

    # Indicadores (atualizados a cada vela de 1min)
    rsi: float = 0.0
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    ema_200: float = 0.0

    # Métricas auxiliares
    volume_24h: float = 0.0
    volume_avg_20: float = 0.0
    volume_ratio: float = 0.0

    # Buffer de velas (200 para calcular EMA 200)
    candles: deque = None

    def __post_init__(self):
        if self.candles is None:
            self.candles = deque(maxlen=200)


class MarketScanner:
    """
    Scanner de mercado com monitoramento tick-by-tick

    COMPONENTE 1: Indicator Calculator (a cada 1 min)
        - WebSocket Kline (velas de 1min)
        - Recalcula RSI, BB, EMA quando vela fecha

    COMPONENTE 2: Entry Monitor (tempo real)
        - WebSocket MiniTicker (preço a cada tick)
        - Verifica condições de entrada A CADA TICK
        - Dispara compra IMEDIATAMENTE quando OK
    """

    def __init__(self, config, exchange_manager, risk_manager, database, telegram_notifier):
        self.config = config
        self.exchange = exchange_manager
        self.risk_manager = risk_manager
        self.db = database
        self.telegram = telegram_notifier

        # Estado do mercado por símbolo
        self.market_states: Dict[str, MarketState] = {}

        # Símbolos ativos
        self.active_symbols: List[str] = []

        # WebSocket connections
        self.ws_kline: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.ws_miniticker: Dict[str, websockets.WebSocketClientProtocol] = {}

        # Flags de buffer pronto
        self.buffer_ready: Dict[str, bool] = {}

        # Reconnection attempts
        self.reconnect_attempts: Dict[str, int] = {}
        self.max_reconnect_attempts = 10

        # Cooldown após bloqueio (evita loop infinito)
        self.blocked_until: Dict[str, datetime] = {}

        # Flag para shutdown
        self.is_running = True
        self.running_tasks: Set[str] = set()
        self.subscribed_streams: Set[str] = set()
        self.ws_main: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_lock = asyncio.Lock()

        # Cache para evitar chamadas de DB a cada tick
        self.open_trades_count = 0

    async def start(self):
        """Inicia o scanner"""
        logger.info("=" * 60)
        logger.info("🚀 MARKET SCANNER START")
        logger.info("=" * 60)

        # Task única para o monitor de WebSockets (Multi-Stream)
        asyncio.create_task(self.monitor_multi_stream())

        # Task para atualizar símbolos dinamicamente
        asyncio.create_task(self.dynamic_symbol_refresher())

        # Task para manter contagem de trades abertos (cache)
        asyncio.create_task(self.open_trades_refresher())

        # Manter o scanner rodando
        while self.is_running:
            await asyncio.sleep(10)

    async def dynamic_symbol_refresher(self):
        """Task que verifica novos símbolos ativos periodicamente"""
        while self.is_running:
            try:
                await self.load_active_symbols()

                for symbol in self.active_symbols:
                    if symbol not in self.running_tasks:
                        logger.info(f"🆕 Iniciando monitoramento dinâmico: {symbol}")
                        # Preencher buffer inicial
                        if await self.fill_initial_buffer(symbol):
                            self.running_tasks.add(symbol)
                            # Assinar streams para este novo símbolo
                            await self.subscribe_symbol(symbol)

            except Exception as e:
                logger.error(f"❌ Erro no refresher dinâmico: {e}")

            await asyncio.sleep(300)  # Verificar a cada 5 minutos

    async def open_trades_refresher(self):
        """Atualiza a contagem de trades abertos periodicamente para cache"""
        while self.is_running:
            try:
                open_trades = self.db.get_open_trades()
                self.open_trades_count = len(open_trades) if open_trades else 0
            except Exception as e:
                logger.error(f"❌ Erro ao atualizar cache de trades: {e}")
            await asyncio.sleep(10)  # Atualiza a cada 10s

    async def load_active_symbols(self):
        """Carrega símbolos ativos do banco"""
        try:

            # Usar método centralizado do banco de dados
            active_coins = self.db.get_active_symbols()

            if active_coins:
                self.active_symbols = [coin['symbol'] for coin in active_coins]
                logger.info(f"✅ {len(self.active_symbols)} símbolos ativos carregados")
            else:
                logger.warning("⚠️ Nenhum símbolo ativo no banco")

        except Exception as e:
            logger.error(f"❌ Erro ao carregar símbolos: {e}")

    async def fill_initial_buffer(self, symbol: str):
        """
        WARM-UP: Carrega 200 velas via REST API
        Necessário para calcular EMA 200
        """
        try:
            logger.info(f"📥 Warm-up: Carregando 200 velas de {symbol}...")

            ohlcv = self.exchange.exchange.fetch_ohlcv(
                symbol,
                timeframe=self.config.TIMEFRAME,
                limit=200
            )

            if len(ohlcv) < 200:
                logger.error(f"❌ Dados insuficientes para {symbol}: {len(ohlcv)}/200 velas")
                return False

            # Criar MarketState
            self.market_states[symbol] = MarketState(
                symbol=symbol,
                last_update=datetime.now(timezone.utc),
                current_price=ohlcv[-1][4],  # Close da última vela
                candles=deque(ohlcv, maxlen=200)
            )

            # Calcular indicadores iniciais
            await self.calculate_indicators(symbol)

            self.buffer_ready[symbol] = True

            return True

        except Exception as e:
            logger.error(f"❌ Erro ao preencher buffer de {symbol}: {e}")
            return False

    async def monitor_multi_stream(self):
        """
        Mantém uma única conexão WebSocket Multi-Stream para todas as moedas.
        Eficiente, economiza recursos e evita timeouts.
        """
        self.reconnect_attempts["multi_stream"] = 0

        while self.is_running:
            try:
                # URL base para Multi-Stream no Binance Futures
                base_url = "wss://fstream.binance.com/stream"

                logger.info("🔌 Conectando WebSocket Multi-Stream Centralizado...")

                async with websockets.connect(
                    base_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as websocket:

                    self.ws_main = websocket
                    self.reconnect_attempts["multi_stream"] = 0

                    # Se já temos símbolos (em caso de reconexão), assinar novamente
                    if self.running_tasks:
                        streams = []
                        for s in self.running_tasks:
                            s_low = s.lower()
                            streams.append(f"{s_low}@kline_{self.config.TIMEFRAME}")
                            streams.append(f"{s_low}@miniTicker")

                        if streams:
                            subscribe_msg = {
                                "method": "SUBSCRIBE",
                                "params": streams,
                                "id": int(datetime.now().timestamp())
                            }
                            await websocket.send(json.dumps(subscribe_msg))
                            self.subscribed_streams.update(streams)
                            logger.info(f"✅ Re-inscrito em {len(streams)} streams em massa")

                    logger.info("✅ WebSocket Multi-Stream conectado e pronto")

                    async for message in websocket:
                        try:
                            data = json.loads(message)

                            # Formato Multi-Stream: {"stream": "...", "data": {...}}
                            if "stream" in data and "data" in data:
                                stream_name = data["stream"]
                                payload = data["data"]

                                # Extrair símbolo do nome do stream (ex: btcusdt@kline_1m -> btcusdt)
                                symbol_from_ws = stream_name.split('@')[0].upper()

                                # Roteamento
                                if "@kline" in stream_name:
                                    if "k" in payload:
                                        await self.process_kline(symbol_from_ws, payload["k"])
                                elif "@miniTicker" in stream_name:
                                    if "c" in payload:
                                        await self.process_entry_tick(symbol_from_ws, float(payload["c"]))

                            # Tratar respostas de confirmação do sistema
                            elif "result" in data and data.get("id"):
                                logger.debug(f"ℹ️ Confirmação WebSocket: {data}")

                        except Exception as e:
                            logger.error(f"❌ Erro ao processar mensagem multi-stream: {e}")

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️ Conexão Multi-Stream fechada: {e}")
                self.ws_main = None
                await self.handle_reconnection("multi_stream")
            except Exception as e:
                logger.error(f"❌ Erro crítico no WebSocket Multi-Stream: {e}")
                self.ws_main = None
                await self.handle_reconnection("multi_stream")

    async def subscribe_symbol(self, symbol: str):
        """Assina os streams de um novo símbolo na conexão aberta"""
        try:
            s_low = symbol.lower()
            new_streams = [
                f"{s_low}@kline_{self.config.TIMEFRAME}",
                f"{s_low}@miniTicker"
            ]

            # Verificar se já estamos conectados
            async with self.ws_lock:
                if self.ws_main and self.ws_main.open:
                    subscribe_msg = {
                        "method": "SUBSCRIBE",
                        "params": new_streams,
                        "id": int(datetime.now().timestamp())
                    }
                    await self.ws_main.send(json.dumps(subscribe_msg))
                    self.subscribed_streams.update(new_streams)
                    logger.info(f"📡 Inscrito em novos streams para {symbol}")
                else:
                    # Se não houver conexão, o loop monitor_multi_stream cuidará da assinatura
                    # quando subir, pois o símbolo já estará em running_tasks
                    logger.debug(f"⏳ Aguardando conexão para inscrever {symbol}")

        except Exception as e:
            logger.error(f"❌ Erro ao inscrever símbolo {symbol}: {e}")

    async def handle_reconnection(self, key: str):
        """Lógica de reconnection"""
        self.reconnect_attempts[key] += 1

        if self.reconnect_attempts[key] > self.max_reconnect_attempts:
            logger.error(f"❌ Máximo de reconnection atingido: {key}")
            return

        wait_time = min(2 ** self.reconnect_attempts[key], 5)
        logger.warning(f"🔄 Reconnection em {wait_time}s: {key}")
        await asyncio.sleep(wait_time)

    async def process_kline(self, symbol: str, kline: dict):
        """
        Processa vela do WebSocket e atualiza indicadores
        """
        try:
            candle = [
                int(kline['t']),  # timestamp
                float(kline['o']),  # open
                float(kline['h']),  # high
                float(kline['l']),  # low
                float(kline['c']),  # close
                float(kline['v'])   # volume
            ]

            is_closed = kline['x']

            if is_closed:
                # Vela fechou - adicionar ao buffer
                state = self.market_states.get(symbol)
                if not state:
                    return

                state.candles.append(candle)
                state.current_price = candle[4]
                state.last_update = datetime.now()

                # logger.info(f"🕐 {symbol}: Vela fechada @ ${candle[4]:.2f}")

                # RECALCULAR INDICADORES
                await self.calculate_indicators(symbol)

        except Exception as e:
            logger.error(f"❌ Erro ao processar kline de {symbol}: {e}")

    async def calculate_indicators(self, symbol: str):
        """
        Calcula todos os indicadores técnicos

        OTIMIZADO: Uma única passada pelos dados
        """
        try:
            state = self.market_states.get(symbol)
            if not state or len(state.candles) < 200:
                return

            from src.indicators import TechnicalIndicators

            candles_list = list(state.candles)
            closes = [c[4] for c in candles_list]
            volumes = [c[5] for c in candles_list]

            # Calcular indicadores
            state.rsi = TechnicalIndicators.calculate_rsi(closes, period=self.config.RSI_PERIOD)
            state.bb_upper, state.bb_middle, state.bb_lower = TechnicalIndicators.calculate_bollinger_bands(
                closes, period=self.config.BB_PERIOD, std_dev=self.config.BB_STD_DEV
            )
            state.ema_200 = TechnicalIndicators.calculate_ema(closes, period=self.config.EMA_PERIOD)

            # Volume médio (últimas 20 velas)
            state.volume_avg_20 = sum(volumes[-20:]) / 20
            state.volume_24h = volumes[-1]
            state.volume_ratio = state.volume_24h / state.volume_avg_20 if state.volume_avg_20 > 0 else 1

            # Use a standard clock emoji or simple text to avoid encoding issues
            logger.info(f"🕐 {symbol}: Fechou @ ${state.current_price:.2f} | RSI: {state.rsi:.2f} | BB Low: ${state.bb_lower:.2f} | EMA: ${state.ema_200:.2f}")

        except Exception as e:
            logger.error(f"❌ Erro ao calcular indicadores de {symbol}: {e}")

    async def process_entry_tick(self, symbol: str, current_price: float):
        """
        Processa tick de preço e verifica condições de ENTRADA

        CRITICAL:
        - Roda A CADA TICK (milissegundos)
        - Verifica indicadores em TEMPO REAL
        - Dispara compra IMEDIATAMENTE quando OK
        """
        try:
            state = self.market_states.get(symbol)
            if not state:
                return

            # Atualizar preço atual
            state.current_price = current_price

            # Verificar se indicadores estão prontos
            if state.rsi == 0 or state.ema_200 == 0:
                return

            # CONDIÇÕES DE ENTRADA (Cálculo prévio para o log)
            condition_rsi = state.rsi < self.config.RSI_OVERSOLD
            condition_bb = current_price <= state.bb_lower * 1.001  # 0.1% de tolerância

            # Log detalhado (a cada 30s para não poluir)
            now = datetime.now(timezone.utc)
            time_since_last = (now - state.last_update).total_seconds()
            if time_since_last >= 30:
                status_msg = f"🔍 {symbol} ${current_price:.2f} | RSI: {state.rsi:.2f} {'✅' if condition_rsi else '❌'} | BB: ${state.bb_lower:.2f} {'✅' if condition_bb else '❌'} | EMA: ${state.ema_200:.2f}"

                # Adicionar aviso se as entradas estão travadas pelo limite de trades
                if self.open_trades_count >= self.config.MAX_OPEN_TRADES:
                    status_msg += f" | ⏸️ (Limite: {self.open_trades_count}/{self.config.MAX_OPEN_TRADES} trades)"

                logger.info(status_msg)
                state.last_update = now

            # PRIORIDADE DE SINAL: Verificação de cache local (ultra rápido)
            if self.open_trades_count >= self.config.MAX_OPEN_TRADES:
                return

            # Verificar cooldown após bloqueio
            now = datetime.now(timezone.utc)
            if symbol in self.blocked_until:
                if now < self.blocked_until[symbol]:
                    return  # Ainda em cooldown
                else:
                    del self.blocked_until[symbol]  # Cooldown expirado

            # Se TODAS as condições OK: EXECUTAR COMPRA IMEDIATAMENTE
            if condition_rsi and condition_bb:
                logger.info(f"🎯 SINAL DE COMPRA: {symbol} | RSI: {state.rsi:.2f} | BB: ${state.bb_lower:.2f} | EMA: ${state.ema_200:.2f}")

                # EXECUTAR TRADE
                await self.execute_entry(symbol, current_price, state)

        except Exception as e:
            logger.error(f"❌ Erro ao processar tick de entrada ({symbol}): {e}")

    async def execute_entry(self, symbol: str, entry_price: float, state: MarketState):
        """
        Executa ENTRADA no trade

        Args:
            symbol: Símbolo
            entry_price: Preço de entrada
            state: Estado do mercado
        """
        try:
            logger.info(f"🚀 Executando entrada em {symbol}...")

            # Validar com RiskManager
            validation = self.risk_manager.validate_trade_entry(symbol)

            if not validation['allowed']:
                logger.warning(f"❌ Entrada bloqueada: {symbol}")
                for reason in validation['reasons']:
                    logger.warning(f"   • {reason}")

                # Adicionar cooldown de 60s para evitar loop infinito
                self.blocked_until[symbol] = datetime.now(timezone.utc) + timedelta(seconds=60)
                logger.info(f"⏰ Cooldown de 60s ativado para {symbol}")
                return

            # Calcular TP e SL baseado nos parâmetros globais (Fixos conforme solicitado)
            # TP Líquido de 0.6% (+ taxas)
            take_profit = entry_price * (1 + self.config.TARGET_PROFIT_NET)

            # SL de 0.8%
            stop_loss = entry_price * (1 - self.config.STOP_LOSS_PERCENTAGE)

            # Preparar indicadores para passar ao execute_trade
            scanner_indicators = {
                'rsi': state.rsi,
                'bb_upper': state.bb_upper,
                'bb_middle': state.bb_middle,
                'bb_lower': state.bb_lower,
                'ema_200': state.ema_200,
                'take_profit': take_profit,
                'stop_loss': stop_loss,
                'volume_ratio': state.volume_ratio
            }

            # Importar e chamar diretamente a função execute_trade
            from src.main import execute_trade

            result = await execute_trade(
                symbol=symbol,
                scanner_validated=True,
                scanner_price=entry_price,
                scanner_indicators=scanner_indicators
            )

            if result.get('success'):
                trade_id = result.get('trade_id')
                logger.info(f"✅ Trade executado com sucesso!")
                logger.info(f"   Trade ID: {trade_id}")

                # Log adicional com indicadores
                self.db.log('INFO', f'Scanner: Trade aberto via detecção automática', {
                    'trade_id': trade_id,
                    'symbol': symbol,
                    'entry_price': entry_price,
                    'rsi': state.rsi,
                    'bb_lower': state.bb_lower,
                    'ema_200': state.ema_200
                }, symbol=symbol, trade_id=trade_id)
            else:
                logger.warning(f"⚠️ Trade não executado: {result.get('message')}")
                logger.warning(f"   Razão: {result.get('reason', 'N/A')}")

                # Adicionar cooldown de 60s se falhou
                self.blocked_until[symbol] = datetime.now() + timedelta(seconds=60)
                logger.info(f"⏰ Cooldown de 60s ativado para {symbol}")

        except Exception as e:
            logger.error(f"❌ Erro ao executar entrada: {e}", exc_info=True)

    async def shutdown(self):
        """Encerra o scanner"""
        logger.info("🛑 Encerrando MarketScanner...")
        self.is_running = False

        if self.ws_main:
            try:
                await self.ws_main.close()
            except:
                pass

        logger.info("✅ MarketScanner encerrado")


async def start_market_scanner(config, exchange_manager, risk_manager, database, telegram_notifier):
    """Função auxiliar para iniciar o scanner"""
    scanner = MarketScanner(config, exchange_manager, risk_manager, database, telegram_notifier)
    await scanner.start()
