"""
Scanner de mercado usando Binance WebSockets REAIS
Monitora preços em tempo real e detecta oportunidades de scalping
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import ccxt
import websockets
from collections import deque

logger = logging.getLogger(__name__)


class BinanceWebSocketScanner:
    """Scanner de mercado em tempo real via Binance WebSockets"""
    
    def __init__(self, config, exchange_manager, risk_manager, database):
        self.config = config
        self.exchange = exchange_manager
        self.risk_manager = risk_manager
        self.db = database
        
        # Cache de velas para cada símbolo (200 para calcular EMA 200)
        self.candles_cache: Dict[str, deque] = {}
        
        # Última vez que cada símbolo foi verificado
        self.last_check: Dict[str, datetime] = {}
        
        # Intervalo mínimo entre verificações (evitar overtrading)
        self.check_interval = timedelta(seconds=self.config.SCANNER_CHECK_INTERVAL)
        
        # Lista de símbolos ativos
        self.active_symbols: List[str] = []
        
        # WebSocket connections
        self.websockets: Dict[str, websockets.WebSocketClientProtocol] = {}
        
        # Flag para saber se buffer inicial está completo
        self.buffer_ready: Dict[str, bool] = {}
        
        # Reconnection attempts
        self.reconnect_attempts: Dict[str, int] = {}
        self.max_reconnect_attempts = 10
        
        logger.info("🔍 Binance WebSocket Scanner inicializado")
    
    async def start(self):
        """Inicia o scanner em background"""
        logger.info("=" * 60)
        logger.info("🚀 INICIANDO BINANCE WEBSOCKET SCANNER")
        logger.info("=" * 60)
        
        # Buscar símbolos ativos do Supabase
        await self.load_active_symbols()
        
        if not self.active_symbols:
            logger.warning("⚠️ Nenhum símbolo ativo encontrado. Scanner pausado.")
            return
        
        logger.info(f"📊 Monitorando {len(self.active_symbols)} símbolos via WebSocket:")
        for symbol in self.active_symbols:
            logger.info(f"   • {symbol}")
        
        # Iniciar loops de monitoramento para cada símbolo
        tasks = [
            asyncio.create_task(self.monitor_symbol_websocket(symbol))
            for symbol in self.active_symbols
        ]
        
        # Aguardar todas as tasks
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def load_active_symbols(self):
        """Carrega lista de símbolos ativos do Supabase"""
        try:
            response = self.db.client.table('coins_config')\
                .select('symbol')\
                .eq('is_active', True)\
                .execute()
            
            if response.data:
                self.active_symbols = [coin['symbol'] for coin in response.data]
                logger.info(f"✅ {len(self.active_symbols)} símbolos ativos carregados")
            else:
                logger.warning("⚠️ Nenhum símbolo ativo no banco de dados")
        except Exception as e:
            logger.error(f"❌ Erro ao carregar símbolos: {e}")
    
    async def fill_initial_buffer(self, symbol: str):
        """
        CRITICAL: Preenche buffer inicial com 200 velas ANTES de começar a analisar
        Necessário para calcular EMA 200 e outros indicadores
        """
        try:
            logger.info(f"📥 Preenchendo buffer inicial de {symbol} (200 velas)...")
            
            # Buscar últimas 200 velas via REST API
            ohlcv = self.exchange.exchange.fetch_ohlcv(
                symbol,
                timeframe=self.config.TIMEFRAME,
                limit=200
            )
            
            if len(ohlcv) < 100:
                logger.error(f"❌ Dados insuficientes para {symbol}: apenas {len(ohlcv)} velas")
                return False
            
            # Inicializar cache
            self.candles_cache[symbol] = deque(ohlcv, maxlen=200)
            
            logger.info(f"✅ Buffer de {symbol} pronto com {len(ohlcv)} velas")
            logger.info(f"   Primeira vela: {datetime.fromtimestamp(ohlcv[0][0]/1000).strftime('%Y-%m-%d %H:%M')}")
            logger.info(f"   Última vela: {datetime.fromtimestamp(ohlcv[-1][0]/1000).strftime('%Y-%m-%d %H:%M')}")
            
            self.buffer_ready[symbol] = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao preencher buffer de {symbol}: {e}")
            self.buffer_ready[symbol] = False
            return False
    
    async def monitor_symbol_websocket(self, symbol: str):
        """
        Monitora um símbolo via WebSocket com reconnection logic
        """
        # Converter símbolo para formato Binance WebSocket (BTCUSDT -> btcusdt)
        ws_symbol = symbol.lower()
        
        # Preencher buffer inicial ANTES de conectar WebSocket
        buffer_filled = await self.fill_initial_buffer(symbol)
        
        if not buffer_filled:
            logger.error(f"❌ Não foi possível preencher buffer de {symbol}. Abortando.")
            return
        
        self.reconnect_attempts[symbol] = 0
        
        while True:
            try:
                # URL do WebSocket da Binance (Kline/Candlestick)
                ws_url = f"wss://stream.binance.com:9443/ws/{ws_symbol}@kline_{self.config.TIMEFRAME}"
                
                logger.info(f"🔌 Conectando WebSocket de {symbol}...")
                
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as websocket:
                    
                    self.websockets[symbol] = websocket
                    self.reconnect_attempts[symbol] = 0
                    
                    logger.info(f"✅ WebSocket de {symbol} conectado!")
                    
                    # Loop principal de recepção de dados
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            
                            # Processar dados da vela
                            if 'k' in data:
                                kline = data['k']
                                
                                # Atualizar cache com nova vela
                                await self.process_kline(symbol, kline)
                                
                        except json.JSONDecodeError as e:
                            logger.error(f"❌ Erro ao decodificar JSON de {symbol}: {e}")
                        except Exception as e:
                            logger.error(f"❌ Erro ao processar mensagem de {symbol}: {e}")
            
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️ WebSocket de {symbol} fechou: {e}")
                await self.handle_reconnection(symbol)
            
            except Exception as e:
                logger.error(f"❌ Erro no WebSocket de {symbol}: {e}")
                await self.handle_reconnection(symbol)
    
    async def handle_reconnection(self, symbol: str):
        """
        CRITICAL: Lógica de reconnection automática
        Reconecta em menos de 5 segundos
        """
        self.reconnect_attempts[symbol] += 1
        
        if self.reconnect_attempts[symbol] > self.max_reconnect_attempts:
            logger.error(f"❌ {symbol}: Máximo de tentativas de reconnection atingido ({self.max_reconnect_attempts})")
            logger.error(f"❌ Abortando monitoramento de {symbol}")
            return
        
        # Backoff exponencial mas limitado a 5 segundos
        wait_time = min(2 ** self.reconnect_attempts[symbol], 5)
        
        logger.warning(f"🔄 Tentativa {self.reconnect_attempts[symbol]}/{self.max_reconnect_attempts} de reconnection para {symbol}")
        logger.warning(f"⏳ Aguardando {wait_time}s antes de reconectar...")
        
        await asyncio.sleep(wait_time)
        
        logger.info(f"🔌 Reconectando {symbol}...")
    
    async def process_kline(self, symbol: str, kline: dict):
        """
        Processa nova vela do WebSocket e atualiza cache
        """
        try:
            # Extrair dados da vela
            # [timestamp, open, high, low, close, volume]
            candle = [
                int(kline['t']),  # Timestamp
                float(kline['o']),  # Open
                float(kline['h']),  # High
                float(kline['l']),  # Low
                float(kline['c']),  # Close
                float(kline['v'])   # Volume
            ]
            
            # Verificar se é uma vela FECHADA (completa)
            is_closed = kline['x']
            
            if is_closed:
                # Vela fechou - adicionar ao cache
                self.candles_cache[symbol].append(candle)
                logger.debug(f"📊 {symbol}: Nova vela fechada @ ${candle[4]:.2f}")
                
                # Analisar símbolo se já passou o intervalo de check
                if self.should_check(symbol):
                    await self.analyze_symbol(symbol)
            else:
                # Vela ainda aberta - atualizar última vela do cache
                if len(self.candles_cache[symbol]) > 0:
                    self.candles_cache[symbol][-1] = candle
                    
        except Exception as e:
            logger.error(f"❌ Erro ao processar kline de {symbol}: {e}")
    
    def should_check(self, symbol: str) -> bool:
        """Verifica se deve analisar o símbolo (respeitar intervalo de SCANNER_CHECK_INTERVAL)"""
        now = datetime.now()
        
        if symbol not in self.last_check:
            self.last_check[symbol] = now
            return True
        
        time_since_last = now - self.last_check[symbol]
        
        if time_since_last >= self.check_interval:
            self.last_check[symbol] = now
            return True
        
        return False
    
    async def analyze_symbol(self, symbol: str):
        """Analisa um símbolo e detecta sinais de entrada"""
        try:
            # Verificar se buffer está pronto
            if not self.buffer_ready.get(symbol, False):
                return
            
            candles = list(self.candles_cache.get(symbol, []))
            
            if len(candles) < 100:
                logger.warning(f"⚠️ {symbol}: Buffer insuficiente ({len(candles)} velas)")
                return
            
            # Extrair preços (OTIMIZADO - uma única iteração)
            closes = []
            highs = []
            lows = []
            volumes = []
            
            for candle in candles:
                highs.append(candle[2])
                lows.append(candle[3])
                closes.append(candle[4])
                volumes.append(candle[5])
            
            current_price = closes[-1]
            
            # Calcular indicadores (OTIMIZADO)
            from src.indicators import TechnicalIndicators
            
            rsi = TechnicalIndicators.calculate_rsi(closes)
            bb_upper, bb_middle, bb_lower = TechnicalIndicators.calculate_bollinger_bands(closes)
            ema_200 = TechnicalIndicators.calculate_ema(closes, period=200)
            atr = TechnicalIndicators.calculate_atr(highs, lows, closes)
            
            # Calcular distância das bandas
            bb_distance = (current_price - bb_lower[-1]) / bb_lower[-1] * 100
            
            # Volume médio (últimas 20 velas)
            avg_volume = sum(volumes[-20:]) / 20
            current_volume = volumes[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            logger.debug(f"📊 {symbol} | ${current_price:.2f} | RSI: {rsi[-1]:.1f} | BB: {bb_distance:.2f}% | Vol: {volume_ratio:.2f}x")
            
            # DETECTAR SINAL DE COMPRA
            signal_detected = self.detect_buy_signal(
                symbol=symbol,
                current_price=current_price,
                rsi=rsi[-1],
                bb_lower=bb_lower[-1],
                bb_distance=bb_distance,
                ema_200=ema_200[-1],
                volume_ratio=volume_ratio
            )
            
            if signal_detected:
                await self.execute_trade_from_signal(
                    symbol=symbol,
                    current_price=current_price,
                    rsi=rsi[-1],
                    bb_distance=bb_distance,
                    volume_ratio=volume_ratio
                )
        
        except Exception as e:
            logger.error(f"❌ Erro ao analisar {symbol}: {e}")
    
    def detect_buy_signal(
        self,
        symbol: str,
        current_price: float,
        rsi: float,
        bb_lower: float,
        bb_distance: float,
        ema_200: float,
        volume_ratio: float
    ) -> bool:
        """
        Detecta sinal de compra baseado em múltiplos indicadores
        
        Estratégia conservadora de scalping:
        - RSI oversold (< 35)
        - Preço perto ou abaixo da banda inferior de Bollinger
        - Preço acima da EMA 200 (uptrend)
        - Volume acima da média
        """
        
        # Condições para sinal de compra
        conditions = {
            'rsi_oversold': rsi < 35,
            'near_bb_lower': bb_distance < 0.5,  # Menos de 0.5% acima da banda inferior
            'uptrend': current_price > ema_200,
            'volume_high': volume_ratio > 1.2  # Volume 20% acima da média
        }
        
        # Contar quantas condições foram atendidas
        met_conditions = sum(conditions.values())
        total_conditions = len(conditions)
        
        # Sinal positivo se 3 de 4 condições atendidas
        if met_conditions >= 3:
            logger.info("=" * 60)
            logger.info(f"🎯 SINAL DE COMPRA DETECTADO: {symbol}")
            logger.info("=" * 60)
            logger.info(f"💵 Preço: ${current_price:.2f}")
            logger.info(f"📊 Condições: {met_conditions}/{total_conditions}")
            for condition, met in conditions.items():
                status = "✅" if met else "❌"
                logger.info(f"   {status} {condition}")
            logger.info("=" * 60)
            return True
        
        return False
    
    async def execute_trade_from_signal(
        self,
        symbol: str,
        current_price: float,
        rsi: float,
        bb_distance: float,
        volume_ratio: float
    ):
        """Executa trade quando sinal é detectado"""
        try:
            logger.info(f"🚀 Iniciando execução de trade para {symbol}...")
            
            # Validar com risk manager
            validation = await self.risk_manager.validate_trade_entry(symbol)
            
            if not validation['allowed']:
                logger.warning(f"❌ Trade bloqueado para {symbol}")
                for reason in validation['reasons']:
                    logger.warning(f"   • {reason}")
                return
            
            logger.info(f"✅ Trade aprovado pelo risk manager")
            logger.info(f"📈 Executando trade de {symbol} via API interna...")
            
            # Fazer requisição interna para o endpoint de trade manual
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://localhost:{self.config.WEBHOOK_PORT}/trade/manual",
                    json={"symbol": symbol, "webhook_price": current_price},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"✅ Trade executado com sucesso!")
                    logger.info(f"   Trade ID: {data.get('trade_id')}")
                else:
                    logger.error(f"❌ Erro ao executar trade: {response.status_code}")
        
        except Exception as e:
            logger.error(f"❌ Erro ao executar trade de sinal: {e}")


async def start_scanner(config, exchange_manager, risk_manager, database):
    """Função auxiliar para iniciar o scanner"""
    scanner = BinanceWebSocketScanner(config, exchange_manager, risk_manager, database)
    await scanner.start()
