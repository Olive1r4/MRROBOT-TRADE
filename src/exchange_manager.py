"""
Gerenciador de Exchange com suporte a modo Mock e Produção
"""
import ccxt
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal
import logging

from src.config import Config

logger = logging.getLogger(__name__)


class MockExecutor:
    """Simulador de execução de ordens para testes"""

    def __init__(self):
        self.mock_orders = {}
        self.order_counter = 1000
        logger.info("🎭 MockExecutor inicializado - Modo simulação ativo")

    def create_market_order(self, symbol: str, side: str, amount: float, **params) -> Dict:
        """Simula criação de ordem de mercado"""
        order_id = f"MOCK_{self.order_counter}"
        self.order_counter += 1

        # Simular um preço de execução (na prática, viria do exchange)
        # Aqui você pode adicionar slippage simulado se quiser
        mock_price = params.get('price', 0)

        order = {
            'id': order_id,
            'symbol': symbol,
            'type': 'market',
            'side': side,
            'amount': amount,
            'price': mock_price,
            'status': 'closed',
            'filled': amount,
            'timestamp': int(time.time() * 1000),
            'datetime': datetime.utcnow().isoformat(),
            'info': {'mock': True}
        }

        self.mock_orders[order_id] = order
        logger.info(f"🎭 MOCK ORDER: {side.upper()} {amount} {symbol} @ {mock_price}")

        return order

    def create_limit_order(self, symbol: str, side: str, amount: float, price: float, **params) -> Dict:
        """Simula criação de ordem limitada"""
        order_id = f"MOCK_{self.order_counter}"
        self.order_counter += 1

        order = {
            'id': order_id,
            'symbol': symbol,
            'type': 'limit',
            'side': side,
            'amount': amount,
            'price': price,
            'status': 'open',
            'filled': 0,
            'timestamp': int(time.time() * 1000),
            'datetime': datetime.utcnow().isoformat(),
            'info': {'mock': True}
        }

        self.mock_orders[order_id] = order
        logger.info(f"🎭 MOCK LIMIT ORDER: {side.upper()} {amount} {symbol} @ {price}")

        return order

    def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """Simula cancelamento de ordem"""
        if order_id in self.mock_orders:
            self.mock_orders[order_id]['status'] = 'canceled'
            logger.info(f"🎭 MOCK ORDER CANCELLED: {order_id}")
            return self.mock_orders[order_id]
        else:
            raise Exception(f"Order {order_id} not found in mock orders")

    def fetch_order(self, order_id: str, symbol: str) -> Dict:
        """Simula busca de ordem"""
        if order_id in self.mock_orders:
            return self.mock_orders[order_id]
        else:
            raise Exception(f"Order {order_id} not found in mock orders")


class ExchangeManager:
    """
    Gerenciador de conexão com a Binance
    Alterna entre modo Mock (simulação) e Prod (real) baseado na variável MODE
    """

    def __init__(self, config: Config):
        self.config = config
        self.mode = config.MODE
        self.exchange = None
        self.mock_executor = None

        self._initialize_exchange()

    def _initialize_exchange(self):
        """Inicializa a conexão com a exchange"""
        try:
            if self.mode == "PROD":
                # Modo produção - conexão real com Binance
                self.exchange = ccxt.binance({
                    'apiKey': self.config.BINANCE_API_KEY,
                    'secret': self.config.BINANCE_SECRET_KEY,
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future',  # Usar Binance Futures
                        'adjustForTimeDifference': True,
                    }
                })

                if self.config.BINANCE_TESTNET:
                    self.exchange.set_sandbox_mode(True)
                    logger.warning("⚠️ Usando Binance Testnet")

                # Testar conexão
                self.exchange.load_markets()
                logger.info("✅ Conectado à Binance Futures (MODO PRODUÇÃO)")

            else:
                # Modo mock - apenas leitura de dados reais, execução simulada
                # Chaves removidas para evitar erros de autenticação em chamadas públicas
                self.exchange = ccxt.binance({
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future',
                    }
                })
                self.exchange.load_markets()
                self.mock_executor = MockExecutor()
                logger.info("✅ Conectado à Binance Futures (MODO SIMULAÇÃO)")
                logger.warning("⚠️ Ordens NÃO serão executadas - apenas simuladas!")

        except Exception as e:
            logger.error(f"❌ Erro ao inicializar exchange: {str(e)}")
            raise

    def get_ticker(self, symbol: str) -> Dict:
        """Obtém ticker atual do símbolo"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            logger.error(f"❌ Erro ao obter ticker de {symbol}: {str(e)}")
            raise

    def get_current_price(self, symbol: str) -> float:
        """Obtém preço atual do símbolo"""
        try:
            ticker = self.get_ticker(symbol)
            return float(ticker['last'])
        except Exception as e:
            logger.error(f"❌ Erro ao obter preço de {symbol}: {str(e)}")
            raise

    def fetch_ohlcv(self, symbol: str, timeframe: str = '5m', limit: int = 500) -> List[List]:
        """
        Obtém dados de candles (OHLCV)
        Retorna: [[timestamp, open, high, low, close, volume], ...]
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            logger.error(f"❌ Erro ao obter OHLCV de {symbol}: {str(e)}")
            raise

    def set_leverage(self, symbol: str, leverage: int):
        """Define a alavancagem para um símbolo"""
        try:
            if self.mode == "PROD":
                self.exchange.set_leverage(leverage, symbol)
                logger.info(f"🔧 Alavancagem de {symbol} definida para {leverage}x")
            else:
                logger.info(f"🎭 MOCK: Alavancagem de {symbol} seria definida para {leverage}x")
        except Exception as e:
            logger.error(f"❌ Erro ao definir alavancagem de {symbol}: {str(e)}")
            raise

    def set_margin_mode(self, symbol: str, margin_mode: str = 'isolated'):
        """Define o modo de margem (isolated ou cross)"""
        try:
            if self.mode == "PROD":
                self.exchange.set_margin_mode(margin_mode, symbol)
                logger.info(f"🔧 Modo de margem de {symbol} definido para {margin_mode}")
            else:
                logger.info(f"🎭 MOCK: Modo de margem de {symbol} seria definido para {margin_mode}")
        except Exception as e:
            # Algumas moedas já podem estar configuradas, ignora erro
            logger.warning(f"⚠️ Não foi possível definir modo de margem: {str(e)}")

    def create_market_buy_order(self, symbol: str, amount: float, price: float = None) -> Dict:
        """Cria ordem de compra a mercado"""
        try:
            if self.mode == "PROD":
                order = self.exchange.create_market_buy_order(symbol, amount)
                logger.info(f"✅ ORDEM DE COMPRA EXECUTADA: {amount} {symbol}")
            else:
                order = self.mock_executor.create_market_order(
                    symbol, 'buy', amount, price=price
                )

            return order
        except Exception as e:
            logger.error(f"❌ Erro ao criar ordem de compra: {str(e)}")
            raise

    def create_market_sell_order(self, symbol: str, amount: float, price: float = None) -> Dict:
        """Cria ordem de venda a mercado"""
        try:
            if self.mode == "PROD":
                order = self.exchange.create_market_sell_order(symbol, amount)
                logger.info(f"✅ ORDEM DE VENDA EXECUTADA: {amount} {symbol}")
            else:
                order = self.mock_executor.create_market_order(
                    symbol, 'sell', amount, price=price
                )

            return order
        except Exception as e:
            logger.error(f"❌ Erro ao criar ordem de venda: {str(e)}")
            raise

    def create_limit_order(self, symbol: str, side: str, amount: float, price: float) -> Dict:
        """Cria ordem limitada (buy ou sell)"""
        try:
            if self.mode == "PROD":
                if side == 'buy':
                    order = self.exchange.create_limit_buy_order(symbol, amount, price)
                else:
                    order = self.exchange.create_limit_sell_order(symbol, amount, price)
                logger.info(f"✅ ORDEM LIMIT {side.upper()} CRIADA: {amount} {symbol} @ {price}")
            else:
                order = self.mock_executor.create_limit_order(symbol, side, amount, price)

            return order
        except Exception as e:
            logger.error(f"❌ Erro ao criar ordem limitada: {str(e)}")
            raise

    def create_stop_loss_order(self, symbol: str, side: str, amount: float, stop_price: float) -> Dict:
        """Cria ordem de stop loss"""
        try:
            if self.mode == "PROD":
                params = {
                    'stopPrice': stop_price,
                    'type': 'STOP_MARKET'
                }
                if side == 'buy':
                    order = self.exchange.create_order(symbol, 'STOP_MARKET', 'buy', amount, None, params)
                else:
                    order = self.exchange.create_order(symbol, 'STOP_MARKET', 'sell', amount, None, params)
                logger.info(f"✅ STOP LOSS CRIADO: {amount} {symbol} @ {stop_price}")
            else:
                order = self.mock_executor.create_limit_order(
                    symbol, side, amount, stop_price
                )
                order['type'] = 'stop_market'
                logger.info(f"🎭 MOCK STOP LOSS: {amount} {symbol} @ {stop_price}")

            return order
        except Exception as e:
            logger.error(f"❌ Erro ao criar stop loss: {str(e)}")
            raise

    def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """Cancela uma ordem"""
        try:
            if self.mode == "PROD":
                order = self.exchange.cancel_order(order_id, symbol)
                logger.info(f"✅ ORDEM CANCELADA: {order_id}")
            else:
                order = self.mock_executor.cancel_order(order_id, symbol)

            return order
        except Exception as e:
            logger.error(f"❌ Erro ao cancelar ordem: {str(e)}")
            raise

    def fetch_balance(self) -> Dict:
        """Obtém saldo da conta"""
        try:
            if self.mode == "PROD":
                balance = self.exchange.fetch_balance()
                return balance
            else:
                # Retornar saldo simulado
                logger.info("🎭 MOCK: Retornando saldo simulado")
                return {
                    'USDT': {
                        'free': 100.0,
                        'used': 0.0,
                        'total': 100.0
                    }
                }
        except Exception as e:
            logger.error(f"❌ Erro ao obter saldo: {str(e)}")
            raise

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Obtém posição aberta para um símbolo"""
        try:
            if self.mode == "PROD":
                positions = self.exchange.fetch_positions([symbol])
                for pos in positions:
                    if pos['symbol'] == symbol and float(pos['contracts']) != 0:
                        return pos
                return None
            else:
                logger.info(f"🎭 MOCK: Verificando posição de {symbol}")
                return None
        except Exception as e:
            logger.error(f"❌ Erro ao obter posição: {str(e)}")
            raise

    def calculate_order_size(self, symbol: str, usdt_amount: float, price: float) -> Tuple[float, float]:
        """
        Calcula o tamanho da ordem baseado no valor em USDT
        Retorna: (quantidade, valor_total)
        """
        try:
            # Obter informações do mercado
            market = self.exchange.market(symbol)

            # Calcular quantidade
            quantity = usdt_amount / price

            # Arredondar para a precisão correta
            precision = market['precision']['amount']
            if precision is not None:
                quantity = self.exchange.amount_to_precision(symbol, quantity)

            # Calcular valor total
            total_value = float(quantity) * price

            logger.info(f"📊 Cálculo de ordem: {quantity} {symbol} = ${total_value:.2f}")

            return float(quantity), total_value
        except Exception as e:
            logger.error(f"❌ Erro ao calcular tamanho da ordem: {str(e)}")
            raise

    def is_market_open(self, symbol: str) -> bool:
        """Verifica se o mercado está aberto para trading"""
        try:
            ticker = self.get_ticker(symbol)
            return ticker is not None and 'last' in ticker
        except:
            return False

    def get_market_info(self, symbol: str) -> Dict:
        """Obtém informações do mercado (limites, precisão, etc)"""
        try:
            market = self.exchange.market(symbol)
            return {
                'symbol': market['symbol'],
                'min_amount': market['limits']['amount']['min'],
                'max_amount': market['limits']['amount']['max'],
                'min_cost': market['limits']['cost']['min'],
                'precision_amount': market['precision']['amount'],
                'precision_price': market['precision']['price'],
            }
        except Exception as e:
            logger.error(f"❌ Erro ao obter informações do mercado: {str(e)}")
            raise
