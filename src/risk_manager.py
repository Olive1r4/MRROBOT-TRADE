"""
Gerenciador de Risco com Guardrails de Segurança
Implementa: Daily Stop Loss, Max Open Trades, Anti-Whipsaw, Rate Limiter
"""
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Gerenciador de risco com múltiplos guardrails de segurança
    """

    def __init__(self, config, database):
        self.config = config
        self.db = database
        # Cache local para rate limiting
        self.orders_in_current_minute = []
        logger.info(f"   📉 Daily Stop Loss: {self.config.DAILY_STOP_LOSS * 100:.1f}%")
        logger.info(f"   🔢 Max Open Trades: {self.config.MAX_OPEN_TRADES}")
        logger.info(f"   ⏱️ Trade Cooldown: {self.config.TRADE_COOLDOWN_SECONDS}s")
        logger.info(f"   🚦 Rate Limit: {self.config.MAX_ORDERS_PER_MINUTE} ordens/minuto")

    async def check_daily_stop_loss(self) -> Tuple[bool, str]:
        """
        Verifica se o circuit breaker do stop loss diário está ativo

        Returns:
            (is_allowed: bool, reason: str)
        """
        try:
            today = datetime.now().date()
            daily_pnl = await self.db.get_daily_pnl(today)

            if not daily_pnl:
                # Primeiro trade do dia
                return True, "Primeiro trade do dia"

            # Verificar se circuit breaker está ativo
            if daily_pnl.get('is_circuit_breaker_active', False):
                activated_at = daily_pnl.get('circuit_breaker_activated_at')
                logger.warning(f"🔴 CIRCUIT BREAKER ATIVO desde {activated_at}")
                return False, f"Circuit breaker ativo - Stop loss diário atingido"

            # Verificar PnL atual
            total_pnl = daily_pnl.get('total_pnl', 0)

            # Assumindo que começamos com 10000 USDT (ajustar conforme necessário)
            # TODO: Pegar saldo real do exchange
            initial_balance = 10000.0
            daily_loss_threshold = initial_balance * self.config.DAILY_STOP_LOSS

            if total_pnl < -daily_loss_threshold:
                # Ativar circuit breaker
                await self.db.activate_circuit_breaker(today)
                logger.error(f"🔴 CIRCUIT BREAKER ATIVADO!")
                logger.error(f"   PnL do dia: ${total_pnl:.2f}")
                logger.error(f"   Threshold: ${-daily_loss_threshold:.2f}")
                logger.error(f"   Trading bloqueado até amanhã!")

                return False, f"Circuit breaker ativado - Perda diária de ${abs(total_pnl):.2f}"

            remaining = daily_loss_threshold + total_pnl
            logger.info(f"💰 PnL do dia: ${total_pnl:.2f} | Margem restante: ${remaining:.2f}")

            return True, "Dentro do limite de perda diária"

        except Exception as e:
            logger.error(f"❌ Erro ao verificar daily stop loss: {str(e)}")
            # Em caso de erro, bloquear por segurança
            return False, f"Erro ao verificar stop loss diário: {str(e)}"

    async def check_max_open_trades(self) -> Tuple[bool, str]:
        """
        Verifica se o número máximo de trades abertos foi atingido

        Returns:
            (is_allowed: bool, reason: str)
        """
        try:
            open_trades = await self.db.get_open_trades()
            open_count = len(open_trades)

            if open_count >= self.config.MAX_OPEN_TRADES:
                logger.warning(f"⚠️ Máximo de trades abertos atingido: {open_count}/{self.config.MAX_OPEN_TRADES}")
                symbols = [trade['symbol'] for trade in open_trades]
                return False, f"Max trades atingido ({open_count}/{self.config.MAX_OPEN_TRADES}): {', '.join(symbols)}"

            logger.info(f"✅ Trades abertos: {open_count}/{self.config.MAX_OPEN_TRADES}")
            return True, f"Trades abertos: {open_count}/{self.config.MAX_OPEN_TRADES}"

        except Exception as e:
            logger.error(f"❌ Erro ao verificar max open trades: {str(e)}")
            return False, f"Erro ao verificar trades abertos: {str(e)}"

    async def check_trade_cooldown(self, symbol: str) -> Tuple[bool, str]:
        """
        Verifica se o cooldown entre trades da mesma moeda foi respeitado

        Args:
            symbol: Símbolo da moeda

        Returns:
            (is_allowed: bool, reason: str)
        """
        try:
            cooldown_data = await self.db.get_trade_cooldown(symbol)

            if not cooldown_data:
                # Primeira vez tradando esta moeda
                return True, "Primeira operação desta moeda"

            cooldown_until = cooldown_data.get('cooldown_until')

            if not cooldown_until:
                return True, "Sem cooldown ativo"

            now = datetime.now()

            # Converter para datetime se for string
            if isinstance(cooldown_until, str):
                cooldown_until = datetime.fromisoformat(cooldown_until.replace('Z', '+00:00'))

            if now < cooldown_until:
                remaining_seconds = (cooldown_until - now).total_seconds()
                logger.warning(f"⏱️ {symbol} em cooldown - {remaining_seconds:.0f}s restantes")
                return False, f"Cooldown ativo - {remaining_seconds:.0f}s restantes"

            logger.info(f"✅ {symbol} fora do período de cooldown")
            return True, "Cooldown expirado"

        except Exception as e:
            logger.error(f"❌ Erro ao verificar trade cooldown: {str(e)}")
            # Em caso de erro, permitir (fail-safe)
            return True, "Erro ao verificar cooldown - permitindo"

    async def set_trade_cooldown(self, symbol: str):
        """
        Define o cooldown para uma moeda após fechar um trade

        Args:
            symbol: Símbolo da moeda
        """
        try:
            now = datetime.now()
            cooldown_until = now + timedelta(seconds=self.config.TRADE_COOLDOWN_SECONDS)

            await self.db.set_trade_cooldown(symbol, now, cooldown_until)

            logger.info(f"⏱️ Cooldown definido para {symbol} até {cooldown_until.strftime('%H:%M:%S')}")

        except Exception as e:
            logger.error(f"❌ Erro ao definir trade cooldown: {str(e)}")

    def check_rate_limit(self) -> Tuple[bool, str]:
        """
        Verifica se o rate limit de ordens por minuto foi excedido

        Returns:
            (is_allowed: bool, reason: str)
        """
        try:
            now = datetime.now()
            current_minute = now.replace(second=0, microsecond=0)

            # Limpar ordens de minutos anteriores
            self.orders_in_current_minute = [
                order_time for order_time in self.orders_in_current_minute
                if order_time >= current_minute
            ]

            order_count = len(self.orders_in_current_minute)

            if order_count >= self.config.MAX_ORDERS_PER_MINUTE:
                logger.warning(f"🚦 Rate limit atingido: {order_count}/{self.config.MAX_ORDERS_PER_MINUTE} ordens neste minuto")
                return False, f"Rate limit atingido ({order_count}/{self.config.MAX_ORDERS_PER_MINUTE})"

            logger.debug(f"✅ Rate limit: {order_count}/{self.config.MAX_ORDERS_PER_MINUTE} ordens neste minuto")
            return True, f"Rate limit OK ({order_count}/{self.config.MAX_ORDERS_PER_MINUTE})"

        except Exception as e:
            logger.error(f"❌ Erro ao verificar rate limit: {str(e)}")
            return False, f"Erro ao verificar rate limit: {str(e)}"

    def register_order(self):
        """Registra uma nova ordem no rate limiter"""
        try:
            now = datetime.now()
            self.orders_in_current_minute.append(now)
            logger.debug(f"📝 Ordem registrada no rate limiter")
        except Exception as e:
            logger.error(f"❌ Erro ao registrar ordem: {str(e)}")

    async def check_symbol_is_active(self, symbol: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Verifica se a moeda está ativa no banco de dados

        Args:
            symbol: Símbolo da moeda

        Returns:
            (is_active: bool, reason: str, config: dict)
        """
        try:
            coin_config = await self.db.get_coin_config(symbol)

            if not coin_config:
                logger.warning(f"⚠️ Moeda {symbol} não encontrada no banco de dados")
                return False, f"Moeda {symbol} não configurada", None

            if not coin_config.get('is_active', False):
                logger.warning(f"⚠️ Moeda {symbol} está desativada")
                return False, f"Moeda {symbol} desativada", coin_config

            logger.info(f"✅ Moeda {symbol} está ativa")
            return True, "Moeda ativa", coin_config

        except Exception as e:
            logger.error(f"❌ Erro ao verificar status da moeda: {str(e)}")
            return False, f"Erro ao verificar moeda: {str(e)}", None

    async def validate_trade_entry(self, symbol: str) -> Dict:
        """
        Valida todas as condições para permitir entrada em um trade

        Args:
            symbol: Símbolo da moeda

        Returns:
            {
                'allowed': bool,
                'reasons': list,
                'coin_config': dict
            }
        """
        logger.info(f"🛡️ Validando entrada de trade para {symbol}...")

        reasons = []
        allowed = True
        coin_config = None

        # 1. Verificar se a moeda está ativa
        is_active, reason, coin_config = await self.check_symbol_is_active(symbol)
        reasons.append(f"Moeda: {reason}")
        if not is_active:
            allowed = False

        # 2. Verificar daily stop loss
        daily_ok, daily_reason = await self.check_daily_stop_loss()
        reasons.append(f"Daily Stop Loss: {daily_reason}")
        if not daily_ok:
            allowed = False

        # 3. Verificar max open trades
        max_trades_ok, max_trades_reason = await self.check_max_open_trades()
        reasons.append(f"Open Trades: {max_trades_reason}")
        if not max_trades_ok:
            allowed = False

        # 4. Verificar cooldown
        cooldown_ok, cooldown_reason = await self.check_trade_cooldown(symbol)
        reasons.append(f"Cooldown: {cooldown_reason}")
        if not cooldown_ok:
            allowed = False

        # 5. Verificar rate limit
        rate_limit_ok, rate_limit_reason = self.check_rate_limit()
        reasons.append(f"Rate Limit: {rate_limit_reason}")
        if not rate_limit_ok:
            allowed = False

        if allowed:
            logger.info(f"✅ Todas as validações passaram para {symbol}")
        else:
            logger.warning(f"❌ Trade bloqueado para {symbol}")

        for reason in reasons:
            logger.info(f"   {reason}")

        return {
            'allowed': allowed,
            'reasons': reasons,
            'coin_config': coin_config
        }

    async def calculate_position_size(self, symbol: str, current_price: float,
                                     coin_config: Optional[Dict] = None) -> Tuple[float, float]:
        """
        Calcula o tamanho da posição baseado em 20% do capital disponível

        Args:
            symbol: Símbolo da moeda
            current_price: Preço atual
            coin_config: Configuração da moeda (opcional)

        Returns:
            (usdt_amount, leverage)
        """
        try:
            # ALAVANCAGEM FORÇADA = 5x
            leverage = self.config.DEFAULT_LEVERAGE

            # TODO: Obter saldo real do exchange
            # Por enquanto, usar valor estimado
            total_capital = 10000.0  # Substituir por self.exchange.get_balance('USDT')

            # POSITION SIZING: 20% do capital
            usdt_amount = total_capital * self.config.POSITION_SIZE_PERCENT

            logger.info(f"💰 Position Sizing ({symbol}):")
            logger.info(f"   Capital Total: ${total_capital:.2f}")
            logger.info(f"   Posição: ${usdt_amount:.2f} ({self.config.POSITION_SIZE_PERCENT * 100:.0f}%)")
            logger.info(f"   Alavancagem: {leverage}x (FORÇADA)")

            return usdt_amount, leverage

        except Exception as e:
            logger.error(f"❌ Erro ao calcular tamanho da posição: {str(e)}")
            # Fallback
            return self.config.DEFAULT_POSITION_SIZE, self.config.DEFAULT_LEVERAGE
