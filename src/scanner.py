"""
Scanner de mercado usando Binance WebSockets
Monitora preços em tempo real e detecta oportunidades de scalping
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import ccxt
from collections import deque

logger = logging.getLogger(__name__)


class MarketScanner:
    """Scanner de mercado em tempo real via Binance API"""
    
    def __init__(self, config, exchange_manager, risk_manager, database):
        self.config = config
        self.exchange = exchange_manager
        self.risk_manager = risk_manager
        self.db = database
        
        # Cache de velas para cada símbolo
        self.candles_cache: Dict[str, deque] = {}
        
        # Última vez que cada símbolo foi verificado
        self.last_check: Dict[str, datetime] = {}
        
        # Intervalo mínimo entre verificações (evitar spam)
        self.check_interval = timedelta(seconds=30)
        
        # Lista de símbolos ativos
        self.active_symbols: List[str] = []
        
        logger.info("🔍 Market Scanner inicializado")
    
    async def start(self):
        """Inicia o scanner em background"""
        logger.info("=" * 60)
        logger.info("🚀 INICIANDO MARKET SCANNER")
        logger.info("=" * 60)
        
        # Buscar símbolos ativos do Supabase
        await self.load_active_symbols()
        
        if not self.active_symbols:
            logger.warning("⚠️ Nenhum símbolo ativo encontrado. Scanner pausado.")
            return
        
        logger.info(f"📊 Monitorando {len(self.active_symbols)} símbolos:")
        for symbol in self.active_symbols:
            logger.info(f"   • {symbol}")
        
        # Iniciar loops de monitoramento
        tasks = [
            asyncio.create_task(self.monitor_symbol(symbol))
            for symbol in self.active_symbols
        ]
        
        # Aguardar todas as tasks
        await asyncio.gather(*tasks)
    
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
    
    async def monitor_symbol(self, symbol: str):
        """Monitora um símbolo específico continuamente"""
        logger.info(f"👁️ Iniciando monitoramento de {symbol}")
        
        # Inicializar cache de velas
        self.candles_cache[symbol] = deque(maxlen=200)  # Guardar últimas 200 velas
        
        while True:
            try:
                # Buscar velas recentes
                await self.update_candles(symbol)
                
                # Verificar se deve analisar (respeitar intervalo)
                if self.should_check(symbol):
                    await self.analyze_symbol(symbol)
                
                # Aguardar antes da próxima iteração (atualização a cada 5 segundos)
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"❌ Erro ao monitorar {symbol}: {e}")
                await asyncio.sleep(10)  # Aguardar mais em caso de erro
    
    async def update_candles(self, symbol: str):
        """Atualiza cache de velas de um símbolo"""
        try:
            # Buscar últimas velas (5m timeframe para scalping)
            ohlcv = self.exchange.exchange.fetch_ohlcv(
                symbol, 
                timeframe=self.config.TIMEFRAME,
                limit=200
            )
            
            # Atualizar cache
            self.candles_cache[symbol] = deque(ohlcv, maxlen=200)
            
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar velas de {symbol}: {e}")
    
    def should_check(self, symbol: str) -> bool:
        """Verifica se deve analisar o símbolo (respeitar intervalo)"""
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
            candles = list(self.candles_cache.get(symbol, []))
            
            if len(candles) < 100:
                return  # Não há dados suficientes
            
            # Extrair preços
            closes = [candle[4] for candle in candles]  # Close price
            highs = [candle[2] for candle in candles]   # High
            lows = [candle[3] for candle in candles]    # Low
            volumes = [candle[5] for candle in candles] # Volume
            
            current_price = closes[-1]
            
            # Calcular indicadores
            from src.indicators import (
                calculate_rsi,
                calculate_bollinger_bands,
                calculate_ema,
                calculate_atr
            )
            
            rsi = calculate_rsi(closes)
            bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(closes)
            ema_200 = calculate_ema(closes, period=200)
            atr = calculate_atr(highs, lows, closes)
            
            # Calcular distância das bandas
            bb_distance = (current_price - bb_lower[-1]) / bb_lower[-1] * 100
            
            # Volume médio
            avg_volume = sum(volumes[-20:]) / 20
            current_volume = volumes[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            logger.debug(f"📊 {symbol} | Preço: ${current_price:.2f} | RSI: {rsi[-1]:.1f} | BB Dist: {bb_distance:.2f}% | Vol: {volume_ratio:.2f}x")
            
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
            logger.info(f"📊 Condições atendidas: {met_conditions}/{total_conditions}")
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
            
            # Importar função de execução de trade do main
            # (Isso será feito via chamada HTTP interna ou compartilhamento de função)
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
    scanner = MarketScanner(config, exchange_manager, risk_manager, database)
    await scanner.start()
