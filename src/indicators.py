"""
Indicadores Técnicos para análise de trading
Implementa: RSI, Bandas de Bollinger, EMA, ATR
"""
import numpy as np
import pandas as pd
from typing import List, Tuple, Dict
import logging

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """Classe para cálculo de indicadores técnicos"""
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """
        Calcula o RSI (Relative Strength Index)
        
        Args:
            prices: Lista de preços de fechamento
            period: Período do RSI (padrão: 14)
        
        Returns:
            Valor do RSI (0-100)
        """
        try:
            if len(prices) < period + 1:
                logger.warning(f"⚠️ Dados insuficientes para RSI. Necessário: {period + 1}, Disponível: {len(prices)}")
                return 50.0  # Neutro
            
            prices_array = np.array(prices)
            deltas = np.diff(prices_array)
            
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            
            # Média móvel exponencial
            avg_gain = pd.Series(gains).ewm(span=period, adjust=False).mean().iloc[-1]
            avg_loss = pd.Series(losses).ewm(span=period, adjust=False).mean().iloc[-1]
            
            if avg_loss == 0:
                return 100.0
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            logger.debug(f"📊 RSI calculado: {rsi:.2f}")
            return float(rsi)
        
        except Exception as e:
            logger.error(f"❌ Erro ao calcular RSI: {str(e)}")
            return 50.0
    
    @staticmethod
    def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Tuple[float, float, float]:
        """
        Calcula as Bandas de Bollinger
        
        Args:
            prices: Lista de preços de fechamento
            period: Período da média móvel (padrão: 20)
            std_dev: Desvio padrão para as bandas (padrão: 2.0)
        
        Returns:
            (banda_superior, banda_média, banda_inferior)
        """
        try:
            if len(prices) < period:
                logger.warning(f"⚠️ Dados insuficientes para Bollinger. Necessário: {period}, Disponível: {len(prices)}")
                current_price = prices[-1] if prices else 0
                return current_price, current_price, current_price
            
            prices_array = np.array(prices[-period:])
            
            # Média móvel simples
            sma = np.mean(prices_array)
            
            # Desvio padrão
            std = np.std(prices_array)
            
            # Bandas
            upper_band = sma + (std_dev * std)
            lower_band = sma - (std_dev * std)
            
            logger.debug(f"📊 Bollinger: Superior={upper_band:.2f}, Média={sma:.2f}, Inferior={lower_band:.2f}")
            
            return float(upper_band), float(sma), float(lower_band)
        
        except Exception as e:
            logger.error(f"❌ Erro ao calcular Bollinger Bands: {str(e)}")
            current_price = prices[-1] if prices else 0
            return current_price, current_price, current_price
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int = 200) -> float:
        """
        Calcula a EMA (Exponential Moving Average)
        
        Args:
            prices: Lista de preços de fechamento
            period: Período da EMA (padrão: 200)
        
        Returns:
            Valor da EMA
        """
        try:
            if len(prices) < period:
                logger.warning(f"⚠️ Dados insuficientes para EMA. Necessário: {period}, Disponível: {len(prices)}")
                return prices[-1] if prices else 0
            
            prices_series = pd.Series(prices)
            ema = prices_series.ewm(span=period, adjust=False).mean().iloc[-1]
            
            logger.debug(f"📊 EMA{period} calculada: {ema:.2f}")
            
            return float(ema)
        
        except Exception as e:
            logger.error(f"❌ Erro ao calcular EMA: {str(e)}")
            return prices[-1] if prices else 0
    
    @staticmethod
    def calculate_atr(ohlcv: List[List], period: int = 14) -> float:
        """
        Calcula o ATR (Average True Range)
        
        Args:
            ohlcv: Lista de dados OHLCV [[timestamp, open, high, low, close, volume], ...]
            period: Período do ATR (padrão: 14)
        
        Returns:
            Valor do ATR
        """
        try:
            if len(ohlcv) < period + 1:
                logger.warning(f"⚠️ Dados insuficientes para ATR. Necessário: {period + 1}, Disponível: {len(ohlcv)}")
                return 0.0
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Calcular True Range
            df['h-l'] = df['high'] - df['low']
            df['h-pc'] = abs(df['high'] - df['close'].shift(1))
            df['l-pc'] = abs(df['low'] - df['close'].shift(1))
            
            df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
            
            # Calcular ATR (média móvel do True Range)
            atr = df['tr'].rolling(window=period).mean().iloc[-1]
            
            logger.debug(f"📊 ATR{period} calculado: {atr:.2f}")
            
            return float(atr)
        
        except Exception as e:
            logger.error(f"❌ Erro ao calcular ATR: {str(e)}")
            return 0.0
    
    @staticmethod
    def calculate_sma(prices: List[float], period: int = 20) -> float:
        """
        Calcula a SMA (Simple Moving Average)
        
        Args:
            prices: Lista de preços de fechamento
            period: Período da SMA (padrão: 20)
        
        Returns:
            Valor da SMA
        """
        try:
            if len(prices) < period:
                logger.warning(f"⚠️ Dados insuficientes para SMA. Necessário: {period}, Disponível: {len(prices)}")
                return prices[-1] if prices else 0
            
            prices_array = np.array(prices[-period:])
            sma = np.mean(prices_array)
            
            logger.debug(f"📊 SMA{period} calculada: {sma:.2f}")
            
            return float(sma)
        
        except Exception as e:
            logger.error(f"❌ Erro ao calcular SMA: {str(e)}")
            return prices[-1] if prices else 0


class SignalAnalyzer:
    """
    Analisador de sinais de entrada baseado em indicadores técnicos
    """
    
    def __init__(self, config):
        self.config = config
        self.indicators = TechnicalIndicators()
    
    def analyze_entry_signal(self, symbol: str, ohlcv_data: List[List], current_price: float) -> Dict:
        """
        Analisa se há sinal de entrada baseado nos indicadores
        
        Args:
            symbol: Símbolo da moeda
            ohlcv_data: Dados OHLCV
            current_price: Preço atual
        
        Returns:
            {
                'should_enter': bool,
                'reason': str,
                'indicators': dict,
                'stop_loss': float,
                'take_profit': float
            }
        """
        try:
            # Extrair preços de fechamento
            close_prices = [candle[4] for candle in ohlcv_data]
            
            # Calcular indicadores
            rsi = self.indicators.calculate_rsi(close_prices, self.config.RSI_PERIOD)
            bb_upper, bb_middle, bb_lower = self.indicators.calculate_bollinger_bands(
                close_prices, self.config.BB_PERIOD, self.config.BB_STD_DEV
            )
            ema200 = self.indicators.calculate_ema(close_prices, self.config.EMA_PERIOD)
            atr = self.indicators.calculate_atr(ohlcv_data, self.config.ATR_PERIOD)
            
            indicators_data = {
                'rsi': rsi,
                'bb_upper': bb_upper,
                'bb_middle': bb_middle,
                'bb_lower': bb_lower,
                'ema200': ema200,
                'atr': atr,
                'current_price': current_price
            }
            
            # Lógica de entrada (LONG apenas - Scalping)
            # Condições:
            # 1. Preço abaixo da banda inferior (sobrevenda)
            # 2. RSI abaixo do nível de sobrevenda
            # 3. Preço acima da EMA200 (tendência de alta)
            
            reasons = []
            should_enter = True
            
            # Filtro de tendência
            if current_price < ema200:
                should_enter = False
                reasons.append(f"Preço ({current_price:.4f}) abaixo da EMA200 ({ema200:.4f}) - tendência de baixa")
            else:
                reasons.append(f"✅ Preço acima da EMA200 - tendência de alta")
            
            # Sinal de sobrevenda (Bollinger)
            if current_price > bb_lower:
                should_enter = False
                reasons.append(f"Preço ({current_price:.4f}) não está abaixo da banda inferior ({bb_lower:.4f})")
            else:
                reasons.append(f"✅ Preço abaixo da banda inferior - sobrevenda")
            
            # Sinal de RSI
            if rsi > self.config.RSI_OVERSOLD:
                should_enter = False
                reasons.append(f"RSI ({rsi:.2f}) acima do nível de sobrevenda ({self.config.RSI_OVERSOLD})")
            else:
                reasons.append(f"✅ RSI em sobrevenda")
            
            # CALCULAR STOP LOSS (CRÍTICO - Risk:Reward 1:1 a 1:1.5)
            if self.config.USE_ATR_STOP:
                # Stop loss dinâmico baseado no ATR (volatilidade)
                stop_loss_distance = atr * self.config.ATR_MULTIPLIER
                stop_loss_percentage = stop_loss_distance / current_price
                
                # Limitar stop loss máximo a MAX_LOSS_PER_TRADE (0.9%)
                if stop_loss_percentage > self.config.MAX_LOSS_PER_TRADE:
                    logger.warning(f"⚠️ ATR stop ({stop_loss_percentage*100:.2f}%) excede máximo ({self.config.MAX_LOSS_PER_TRADE*100:.2f}%)")
                    stop_loss_percentage = self.config.MAX_LOSS_PER_TRADE
                    stop_loss_distance = current_price * stop_loss_percentage
                
                # Garantir stop mínimo de 0.3% (evitar stops muito apertados)
                elif stop_loss_percentage < 0.003:
                    logger.warning(f"⚠️ ATR stop ({stop_loss_percentage*100:.2f}%) muito apertado, usando 0.3% mínimo")
                    stop_loss_percentage = 0.003
                    stop_loss_distance = current_price * stop_loss_percentage
                
                stop_loss = current_price - stop_loss_distance
                
            else:
                # Stop loss fixo
                stop_loss_distance = current_price * self.config.STOP_LOSS_PERCENTAGE
                stop_loss = current_price - stop_loss_distance
                stop_loss_percentage = self.config.STOP_LOSS_PERCENTAGE
            
            # Calcular take profit baseado no alvo de lucro
            take_profit = current_price * (1 + self.config.TARGET_PROFIT + (self.config.TRADING_FEE * 2))
            
            # Calcular Risk:Reward Ratio
            risk = stop_loss_distance / current_price
            reward = (take_profit - current_price) / current_price
            risk_reward_ratio = reward / risk if risk > 0 else 0
            
            logger.info(f"💹 Risk:Reward Ratio: 1:{risk_reward_ratio:.2f} (Risk: {risk*100:.2f}% | Reward: {reward*100:.2f}%)")
            
            reason_text = " | ".join(reasons)
            
            logger.info(f"📊 Análise de {symbol}:")
            logger.info(f"   RSI: {rsi:.2f} | BB: [{bb_lower:.4f}, {bb_middle:.4f}, {bb_upper:.4f}]")
            logger.info(f"   EMA200: {ema200:.4f} | ATR: {atr:.4f} | Preço: {current_price:.4f}")
            logger.info(f"   Sinal de entrada: {'✅ SIM' if should_enter else '❌ NÃO'}")
            logger.info(f"   Razões: {reason_text}")
            
            if should_enter:
                logger.info(f"   🎯 Take Profit: {take_profit:.4f} (+{self.config.TARGET_PROFIT * 100:.2f}%)")
                logger.info(f"   🛑 Stop Loss: {stop_loss:.4f} (-{stop_loss_percentage * 100:.2f}%)")
                logger.info(f"   ⚖️ Risk:Reward = 1:{risk_reward_ratio:.2f}")
            
            return {
                'should_enter': should_enter,
                'reason': reason_text,
                'indicators': indicators_data,
                'stop_loss': stop_loss,
                'take_profit': take_profit
            }
        
        except Exception as e:
            logger.error(f"❌ Erro ao analisar sinal de entrada: {str(e)}")
            return {
                'should_enter': False,
                'reason': f"Erro na análise: {str(e)}",
                'indicators': {},
                'stop_loss': 0,
                'take_profit': 0
            }
    
    def check_exit_conditions(self, entry_price: float, current_price: float, 
                             stop_loss: float, take_profit: float) -> Tuple[bool, str]:
        """
        Verifica se as condições de saída foram atingidas
        
        Args:
            entry_price: Preço de entrada
            current_price: Preço atual
            stop_loss: Preço de stop loss
            take_profit: Preço de take profit
        
        Returns:
            (should_exit: bool, reason: str)
        """
        try:
            # Verificar take profit
            if current_price >= take_profit:
                profit_pct = ((current_price - entry_price) / entry_price) * 100
                return True, f"Take profit atingido: {current_price:.4f} (lucro: {profit_pct:.2f}%)"
            
            # Verificar stop loss
            if current_price <= stop_loss:
                loss_pct = ((current_price - entry_price) / entry_price) * 100
                return True, f"Stop loss atingido: {current_price:.4f} (perda: {loss_pct:.2f}%)"
            
            return False, "Aguardando condições de saída"
        
        except Exception as e:
            logger.error(f"❌ Erro ao verificar condições de saída: {str(e)}")
            return False, f"Erro: {str(e)}"
