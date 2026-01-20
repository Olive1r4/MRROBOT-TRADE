"""
Market Scanner com Monitoramento Tick-by-Tick para ENTRADA
Atualiza indicadores a cada 1 minuto (vela fechada)
Verifica condições de entrada A CADA TICK (tempo real)
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
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

        # Flag para shutdown
        self.is_running = True

        # Flag para shutdown
        self.is_running = True

    async def start(self):
        """Inicia o scanner"""
        logger.info("=" * 60)
        logger.info("🚀 MARKET SCANNER START")
        logger.info("=" * 60)

        # Carregar símbolos ativos
        await self.load_active_symbols()

        if not self.active_symbols:
            logger.warning("⚠️ Nenhum símbolo ativo. Scanner pausado.")
            return

        active_list = ", ".join(self.active_symbols)
        logger.info(f"📊 Monitorando ({len(self.active_symbols)}): {active_list}")

        # Iniciar tasks para cada símbolo
        # Cada símbolo terá 2 WebSockets: Kline (indicadores) + MiniTicker (entrada)
        tasks = []
        for symbol in self.active_symbols:
            # Task 1: Kline (atualiza indicadores)
            tasks.append(asyncio.create_task(self.monitor_kline(symbol)))

            # Task 2: MiniTicker (verifica entrada tick-by-tick)
            tasks.append(asyncio.create_task(self.monitor_miniticker(symbol)))

        # Aguardar todas as tasks
        await asyncio.gather(*tasks, return_exceptions=True)

    async def load_active_symbols(self):
        """Carrega símbolos ativos do banco"""
        try:

            # Usar método centralizado do banco de dados
            active_coins = await self.db.get_active_symbols()

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
                last_update=datetime.now(),
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

    async def monitor_kline(self, symbol: str):
        """
        WebSocket de KLINE (velas de 1min)
        Atualiza indicadores a cada vela fechada
        """
        # Preencher buffer inicial ANTES de conectar
        if not await self.fill_initial_buffer(symbol):
            logger.error(f"❌ Abortando monitoramento de {symbol}")
            return

        ws_symbol = symbol.lower()
        self.reconnect_attempts[f"{symbol}_kline"] = 0

        while self.is_running:
            try:
                ws_url = f"wss://fstream.binance.com/ws/{ws_symbol}@kline_{self.config.TIMEFRAME}"

                logger.info(f"🔌 Conectando Kline WebSocket: {symbol}...")

                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as websocket:

                    self.ws_kline[symbol] = websocket
                    self.reconnect_attempts[f"{symbol}_kline"] = 0

                    logger.info(f"✅ Kline WebSocket conectado: {symbol}")

                    async for message in websocket:
                        try:
                            data = json.loads(message)

                            if 'k' in data:
                                kline = data['k']

                                # Processar vela
                                await self.process_kline(symbol, kline)

                        except Exception as e:
                            logger.error(f"❌ Erro ao processar kline de {symbol}: {e}")

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️ Kline WebSocket fechou ({symbol}): {e}")
                await self.handle_reconnection(f"{symbol}_kline")

            except Exception as e:
                logger.error(f"❌ Erro no Kline WebSocket ({symbol}): {e}")
                await self.handle_reconnection(f"{symbol}_kline")

    async def monitor_miniticker(self, symbol: str):
        """
        WebSocket de MINITICKER (preço em tempo real)
        Verifica condições de ENTRADA a cada tick
        """
        # Aguardar buffer estar pronto
        while not self.buffer_ready.get(symbol, False):
            await asyncio.sleep(1)

        ws_symbol = symbol.lower()
        self.reconnect_attempts[f"{symbol}_ticker"] = 0

        while self.is_running:
            try:
                ws_url = f"wss://fstream.binance.com/ws/{ws_symbol}@miniTicker"

                logger.info(f"🔌 Conectando MiniTicker WebSocket: {symbol}...")

                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as websocket:

                    self.ws_miniticker[symbol] = websocket
                    self.reconnect_attempts[f"{symbol}_ticker"] = 0

                    logger.info(f"✅ MiniTicker WebSocket conectado: {symbol}")

                    async for message in websocket:
                        try:
                            data = json.loads(message)

                            if 'c' in data:  # 'c' = close price
                                current_price = float(data['c'])

                                # Processar tick de ENTRADA
                                await self.process_entry_tick(symbol, current_price)

                        except Exception as e:
                            logger.error(f"❌ Erro ao processar tick de {symbol}: {e}")

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️ MiniTicker WebSocket fechou ({symbol}): {e}")
                await self.handle_reconnection(f"{symbol}_ticker")

            except Exception as e:
                logger.error(f"❌ Erro no MiniTicker WebSocket ({symbol}): {e}")
                await self.handle_reconnection(f"{symbol}_ticker")

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

            # CONDIÇÕES DE ENTRADA (VERIFICADAS A CADA TICK)
            # 1. RSI < 25 (oversold)
            # 2. Preço tocou/rompeu BB Lower
            # 3. Preço acima EMA 200 (uptrend)

            condition_rsi = state.rsi < self.config.RSI_OVERSOLD
            condition_bb = current_price <= state.bb_lower * 1.001  # 0.1% de tolerância
            condition_ema = current_price > state.ema_200

            # Log detalhado (a cada 30s para não poluir)
            time_since_last = (datetime.now() - state.last_update).total_seconds()
            if time_since_last >= 30:
                logger.info(f"🔍 {symbol} ${current_price:.2f} | RSI: {state.rsi:.2f} {'✅' if condition_rsi else '❌'} | BB: ${state.bb_lower:.2f} {'✅' if condition_bb else '❌'} | EMA: ${state.ema_200:.2f} {'✅' if condition_ema else '❌'}")

                state.last_update = datetime.now()

            # Se TODAS as condições OK: EXECUTAR COMPRA IMEDIATAMENTE
            if condition_rsi and condition_bb and condition_ema:
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
            validation = await self.risk_manager.validate_trade_entry(symbol)

            if not validation['allowed']:
                logger.warning(f"❌ Entrada bloqueada: {symbol}")
                for reason in validation['reasons']:
                    logger.warning(f"   • {reason}")
                return

            # Fazer requisição interna para o endpoint de trade
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://localhost:{self.config.WEBHOOK_PORT}/trade/manual",
                    json={
                        "symbol": symbol,
                        "webhook_price": entry_price,
                        "indicators": {
                            "rsi": state.rsi,
                            "bb_lower": state.bb_lower,
                            "ema_200": state.ema_200
                        }
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"✅ Trade executado com sucesso!")
                    logger.info(f"   Trade ID: {data.get('trade_id')}")
                else:
                    logger.error(f"❌ Erro ao executar trade: {response.status_code}")

        except Exception as e:
            logger.error(f"❌ Erro ao executar entrada: {e}")

    async def shutdown(self):
        """Encerra o scanner"""
        logger.info("🛑 Encerrando MarketScanner...")
        self.is_running = False

        for symbol, ws in {**self.ws_kline, **self.ws_miniticker}.items():
            try:
                await ws.close()
            except:
                pass

        logger.info("✅ MarketScanner encerrado")


async def start_market_scanner(config, exchange_manager, risk_manager, database, telegram_notifier):
    """Função auxiliar para iniciar o scanner"""
    scanner = MarketScanner(config, exchange_manager, risk_manager, database, telegram_notifier)
    await scanner.start()
