"""
Notificações via Telegram
"""
import httpx
import logging
import html
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Classe para enviar notificações via Telegram"""

    def __init__(self, bot_token: Optional[str], chat_id: Optional[str]):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)

        if self.enabled:
            logger.info("✅ Notificações Telegram habilitadas")
        else:
            logger.info("⚠️ Notificações Telegram desabilitadas (configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID)")

    async def send_message(self, message: str, parse_mode: str = "HTML"):
        """
        Envia mensagem para o Telegram

        Args:
            message: Texto da mensagem
            parse_mode: Modo de parsing (HTML ou Markdown)
        """
        if not self.enabled:
            return

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": parse_mode
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    logger.debug("✅ Mensagem Telegram enviada")
                else:
                    logger.error(f"❌ Erro ao enviar Telegram: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"❌ Erro ao enviar notificação Telegram: {repr(e)}", exc_info=True)

    async def notify_startup(self, config):
        """Notifica inicialização do bot"""
        if not self.enabled:
            return

        mode_emoji = "🎭" if config.MODE == "MOCK" else "⚠️"
        mode_text = "SIMULAÇÃO" if config.MODE == "MOCK" else "PRODUÇÃO"

        message = f"""
🤖 <b>BOT DE SCALPING INICIADO</b>

{mode_emoji} <b>Modo:</b> {mode_text}
🎯 <b>Lucro alvo:</b> {config.TARGET_PROFIT * 100:.2f}%
📈 <b>Timeframe:</b> {config.TIMEFRAME}
🛡️ <b>Stop loss diário:</b> {config.DAILY_STOP_LOSS * 100:.1f}%
🔢 <b>Max trades:</b> {config.MAX_OPEN_TRADES}
⚡ <b>Alavancagem:</b> {config.DEFAULT_LEVERAGE}x

{mode_emoji if config.MODE == "MOCK" else "⚠️"} {
    "Ordens serão SIMULADAS" if config.MODE == "MOCK" else "⚠️ ORDENS REAIS SERÃO EXECUTADAS!"
}

⏰ <i>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>
"""

        await self.send_message(message.strip())

    async def notify_trade_open(self, trade_data: Dict, signal_data: Dict):
        """
        Notifica abertura de trade

        Args:
            trade_data: Dados do trade
            signal_data: Dados dos indicadores
        """
        if not self.enabled:
            return

        symbol = html.escape(str(trade_data.get('symbol', 'N/A')))
        entry_price = float(trade_data.get('entry_price', 0))
        quantity = float(trade_data.get('quantity', 0))
        leverage = int(trade_data.get('leverage', 1))
        target_price = float(trade_data.get('target_price', 0))
        stop_loss_price = float(trade_data.get('stop_loss_price', 0))
        mode = trade_data.get('mode', 'MOCK')

        # Calcular valores
        # position_value já contempla a alavancagem via quantity
        position_value = entry_price * quantity
        target_profit_pct = ((target_price - entry_price) / entry_price) * 100
        stop_loss_pct = ((stop_loss_price - entry_price) / entry_price) * 100

        # Indicadores
        indicators = signal_data.get('indicators', {})
        rsi = indicators.get('rsi', 0)
        current_price = indicators.get('current_price', entry_price)

        mode_emoji = "🎭" if mode == "MOCK" else "💰"

        message = f"""
{mode_emoji} <b>COMPRA EXECUTADA</b>

💎 <b>Moeda:</b> {symbol}
💰 <b>Preço entrada:</b> ${entry_price:,.4f}
📊 <b>Quantidade:</b> {quantity}
⚡ <b>Alavancagem:</b> {leverage}x
💵 <b>Valor posição:</b> ${position_value:,.2f}

🎯 <b>Take Profit:</b> ${target_price:,.4f} (+{target_profit_pct:.2f}%)
🛑 <b>Stop Loss:</b> ${stop_loss_price:,.4f} ({stop_loss_pct:.2f}%)

📈 <b>Indicadores:</b>
  • RSI: {rsi:.1f}
  • Preço: ${current_price:,.4f}

{mode_emoji} <i>{"Ordem SIMULADA" if mode == "MOCK" else "Ordem REAL"}</i>

⏰ <i>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>
"""

        await self.send_message(message.strip())

    async def notify_trade_close(self, trade_data: Dict, exit_price: float, pnl: float, pnl_percentage: float):
        """
        Notifica fechamento de trade

        Args:
            trade_data: Dados do trade
            exit_price: Preço de saída
            pnl: Lucro/prejuízo em dinheiro
            pnl_percentage: Lucro/prejuízo em porcentagem
        """
        if not self.enabled:
            return

        symbol = html.escape(str(trade_data.get('symbol', 'N/A')))
        entry_price = float(trade_data.get('entry_price', 0))
        quantity = float(trade_data.get('quantity', 0))
        leverage = int(trade_data.get('leverage', 1))
        mode = trade_data.get('mode', 'MOCK')
        entry_time = trade_data.get('entry_time')

        # Determinar se foi lucro ou prejuízo
        is_profit = pnl > 0
        result_emoji = "✅" if is_profit else "❌"
        result_text = "LUCRO" if is_profit else "PREJUÍZO"

        mode_emoji = "🎭" if mode == "MOCK" else "💰"

        # Calcular tempo de operação
        duration = "N/A"
        if entry_time:
            try:
                if isinstance(entry_time, str):
                    entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                else:
                    entry_dt = entry_time
                duration_minutes = (datetime.now() - entry_dt.replace(tzinfo=None)).total_seconds() / 60
                duration = f"{int(duration_minutes)} min"
            except:
                pass

        # Calcular valores
        # position_value já contempla a alavancagem via quantity
        position_value = entry_price * quantity

        message = f"""
{result_emoji} <b>VENDA EXECUTADA - {result_text}</b>

💎 <b>Moeda:</b> {symbol}
💰 <b>Preço entrada:</b> ${entry_price:,.4f}
💰 <b>Preço saída:</b> ${exit_price:,.4f}
📊 <b>Quantidade:</b> {quantity}
⚡ <b>Alavancagem:</b> {leverage}x
💵 <b>Valor posição:</b> ${position_value:,.2f}

{result_emoji} <b>Resultado:</b>
  • PnL: {'$' if pnl >= 0 else '-$'}{abs(pnl):,.2f}
  • PnL %: {pnl_percentage:+.2f}%
  • Duração: {duration}

{mode_emoji} <i>{"Ordem SIMULADA" if mode == "MOCK" else "Ordem REAL"}</i>

⏰ <i>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>
"""

        await self.send_message(message.strip())

    async def notify_circuit_breaker(self, daily_pnl: float, threshold: float):
        """Notifica ativação do circuit breaker"""
        if not self.enabled:
            return

        message = f"""
🔴 <b>CIRCUIT BREAKER ATIVADO!</b>

⚠️ O limite de perda diária foi atingido!

📉 <b>PnL do dia:</b> -${abs(daily_pnl):,.2f}
🛑 <b>Limite:</b> ${threshold:,.2f}

🚫 <b>Trading bloqueado até amanhã!</b>

⏰ <i>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>
"""

        await self.send_message(message.strip())

    async def notify_error(self, error_message: str, details: Optional[str] = None):
        """Notifica erro crítico"""
        if not self.enabled:
            return

        message = f"""
❌ <b>ERRO NO BOT</b>

🔴 <b>Mensagem:</b> {error_message}
"""

        if details:
            message += f"\n📝 <b>Detalhes:</b> {details}"

        message += f"\n\n⏰ <i>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>"

        await self.send_message(message.strip())

    async def notify_daily_summary(self, stats: Dict):
        """Notifica resumo diário"""
        if not self.enabled:
            return

        total_pnl = stats.get('total_pnl', 0)
        total_trades = stats.get('total_trades', 0)
        winning_trades = stats.get('winning_trades', 0)
        losing_trades = stats.get('losing_trades', 0)
        win_rate = stats.get('win_rate', 0)

        result_emoji = "✅" if total_pnl >= 0 else "❌"

        message = f"""
📊 <b>RESUMO DIÁRIO</b>

{result_emoji} <b>PnL Total:</b> {'$' if total_pnl >= 0 else '-$'}{abs(total_pnl):,.2f}

📈 <b>Trades:</b>
  • Total: {total_trades}
  • Ganhos: {winning_trades} ✅
  • Perdas: {losing_trades} ❌
  • Win Rate: {win_rate:.1f}%

⏰ <i>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>
"""

        await self.send_message(message.strip())
