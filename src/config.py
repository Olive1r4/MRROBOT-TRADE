"""
Configurações e validação de variáveis de ambiente
"""
import os
from typing import Optional
from pydantic import validator, Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()


class Config(BaseSettings):
    """Configurações do bot com validação automática"""

    # ============================================
    # MODO DE OPERAÇÃO
    # ============================================
    MODE: str = Field(default="MOCK", description="MOCK ou PROD")

    # ============================================
    # BINANCE API
    # ============================================
    BINANCE_API_KEY: str = Field(..., description="Chave da API Binance")
    BINANCE_SECRET_KEY: str = Field(..., description="Secret da API Binance")
    BINANCE_TESTNET: bool = Field(default=False, description="Usar testnet?")

    # ============================================
    # SUPABASE
    # ============================================
    SUPABASE_URL: str = Field(..., description="URL do projeto Supabase")
    SUPABASE_KEY: str = Field(..., description="Chave anon do Supabase")

    # ============================================
    # WEBHOOK
    # ============================================
    WEBHOOK_PORT: int = Field(default=8000, description="Porta do webhook")
    WEBHOOK_SECRET: str = Field(..., description="Token secreto para validar webhooks")

    # ============================================
    # CONFIGURAÇÕES DE TRADING
    # ============================================
    TARGET_PROFIT: float = Field(default=0.006, description="Lucro alvo BRUTO (0.6%)")
    TRADING_FEE: float = Field(default=0.0004, description="Taxa de trading (0.04% por ordem)")

    # LUCRO LÍQUIDO = TARGET_PROFIT + (TRADING_FEE * 2)
    # Para 0.6% líquido: TARGET_PROFIT_NET = 0.006 + 0.0008 = 0.0068 (0.68%)
    TARGET_PROFIT_NET: float = Field(default=0.0068, description="Lucro alvo LÍQUIDO após fees (0.68%)")

    # STOP LOSS POR TRADE (FIXO)
    # Risk:Reward = 0.8:0.6 = 1:0.75 (aceitável para scalping de alta frequência)
    STOP_LOSS_PERCENTAGE: float = Field(default=0.008, description="Stop loss FIXO por trade (0.8%)")
    MAX_LOSS_PER_TRADE: float = Field(default=0.008, description="Perda máxima por trade (0.8%)")
    USE_ATR_STOP: bool = Field(default=False, description="DESABILITADO: Usar stop loss fixo")

    # ALAVANCAGEM (FORÇADA para scalping)
    DEFAULT_LEVERAGE: int = Field(default=5, description="Alavancagem FORÇADA (5x)")
    MAX_LEVERAGE: int = Field(default=5, description="Alavancagem máxima (5x)")

    # POSITION SIZING (20% do capital por operação)
    POSITION_SIZE_PERCENT: float = Field(default=0.20, description="Percentual do capital por trade (20%)")
    DEFAULT_POSITION_SIZE: float = Field(default=100.00, description="Tamanho padrão (será calculado dinamicamente)")

    # ============================================
    # INDICADORES TÉCNICOS (SCALPING DE ALTA PRECISÃO)
    # ============================================
    # Setup Técnico Timeframe 1M:
    # - RSI(7): Mais responsivo para detectar oversold rápido
    # - BB(20, 2.5): Bandas mais largas (2.5 std) para evitar falsos sinais
    # - EMA(200): Filtro de tendência de longo prazo

    RSI_PERIOD: int = Field(default=7, description="Período do RSI (ultra responsivo)")
    RSI_OVERSOLD: float = Field(default=30, description="RSI < 30 = oversold")
    RSI_OVERBOUGHT: float = Field(default=70, description="Nível de sobrecompra do RSI")

    BB_PERIOD: int = Field(default=20, description="Período das Bandas de Bollinger")
    BB_STD_DEV: float = Field(default=2.0, description="Desvio padrão 2.0 (padrão)")

    EMA_PERIOD: int = Field(default=200, description="EMA 200 para filtro de tendência")

    ATR_PERIOD: int = Field(default=14, description="Período do ATR (não usado para stop)")

    TIMEFRAME: str = Field(default="1m", description="Timeframe 1 MINUTO (scalping)")

    # ============================================
    # GUARDRAILS DE SEGURANÇA (SCALPING DE ALTA FREQUÊNCIA)
    # ============================================
    DAILY_STOP_LOSS: float = Field(default=0.03, description="Circuit breaker diário (-3%)")
    MAX_OPEN_TRADES: int = Field(default=1, description="Máximo 1 trade aberto (evitar overtrading)")
    TRADE_COOLDOWN_SECONDS: int = Field(default=900, description="Cooldown 15 minutos (900s)")
    MAX_ORDERS_PER_MINUTE: int = Field(default=10, description="Rate limit 10 ordens/min")

    # ============================================
    # SCANNER DE MERCADO
    # ============================================
    ENABLE_SCANNER: bool = Field(default=True, description="Habilitar scanner automático de mercado")
    SCANNER_CHECK_INTERVAL: int = Field(default=5, description="Intervalo entre análises (5s para não perder velas de 1min)")

    # ============================================
    # LOGGING
    # ============================================
    LOG_LEVEL: str = Field(default="INFO", description="Nível de log")
    LOG_FILE: str = Field(default="logs/scalping_bot.log", description="Arquivo de log")

    # ============================================
    # NOTIFICAÇÕES (OPCIONAL)
    # ============================================
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, description="Token do bot Telegram")
    TELEGRAM_CHAT_ID: Optional[str] = Field(default=None, description="Chat ID do Telegram")
    TELEGRAM_ENABLED: bool = Field(default=False, description="Habilitar notificações Telegram")
    DISCORD_WEBHOOK_URL: Optional[str] = Field(default=None, description="Webhook do Discord")

    # ============================================
    # VALIDADORES
    # ============================================

    @validator("MODE")
    def validate_mode(cls, v):
        """Valida que o modo é MOCK ou PROD"""
        if v not in ["MOCK", "PROD"]:
            raise ValueError("MODE deve ser 'MOCK' ou 'PROD'")
        return v.upper()

    @validator("TARGET_PROFIT")
    def validate_target_profit(cls, v):
        """Valida que o lucro alvo é positivo e razoável"""
        if v <= 0:
            raise ValueError("TARGET_PROFIT deve ser maior que 0")
        if v > 0.1:  # 10%
            raise ValueError("TARGET_PROFIT muito alto (máximo 10%)")
        return v

    @validator("TRADING_FEE")
    def validate_trading_fee(cls, v):
        """Valida que a taxa é positiva"""
        if v < 0:
            raise ValueError("TRADING_FEE não pode ser negativa")
        return v

    @validator("DEFAULT_LEVERAGE")
    def validate_leverage(cls, v):
        """Valida que a alavancagem está dentro dos limites"""
        if v < 1 or v > 125:
            raise ValueError("DEFAULT_LEVERAGE deve estar entre 1 e 125")
        return v

    @validator("RSI_OVERSOLD", "RSI_OVERBOUGHT")
    def validate_rsi_levels(cls, v):
        """Valida que os níveis de RSI estão entre 0 e 100"""
        if v < 0 or v > 100:
            raise ValueError("Níveis de RSI devem estar entre 0 e 100")
        return v

    @validator("DAILY_STOP_LOSS")
    def validate_daily_stop_loss(cls, v):
        """Valida que o stop loss diário é razoável"""
        if v <= 0:
            raise ValueError("DAILY_STOP_LOSS deve ser maior que 0")
        if v > 0.5:  # 50%
            raise ValueError("DAILY_STOP_LOSS muito alto (máximo 50%)")
        return v

    @validator("MAX_OPEN_TRADES")
    def validate_max_open_trades(cls, v):
        """Valida que o número de trades simultâneos é razoável"""
        if v < 1:
            raise ValueError("MAX_OPEN_TRADES deve ser pelo menos 1")
        if v > 10:
            raise ValueError("MAX_OPEN_TRADES muito alto (máximo 10)")
        return v

    @validator("TIMEFRAME")
    def validate_timeframe(cls, v):
        """Valida que o timeframe é válido"""
        valid_timeframes = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"]
        if v not in valid_timeframes:
            raise ValueError(f"TIMEFRAME deve ser um dos seguintes: {', '.join(valid_timeframes)}")
        return v

    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """Valida que o nível de log é válido"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL deve ser um dos seguintes: {', '.join(valid_levels)}")
        return v.upper()

    class Config:
        env_file = ".env"
        case_sensitive = True


# Instância global das configurações
def get_config() -> Config:
    """Retorna a instância das configurações validadas"""
    try:
        config = Config()
        return config
    except Exception as e:
        raise RuntimeError(f"Erro ao carregar configurações: {str(e)}")


# Validar configurações ao importar o módulo
if __name__ == "__main__":
    try:
        config = get_config()
        print("✅ Configurações validadas com sucesso!")
        print(f"📊 Modo: {config.MODE}")
        print(f"🎯 Lucro alvo: {config.TARGET_PROFIT * 100:.2f}%")
        print(f"🛡️ Stop loss diário: {config.DAILY_STOP_LOSS * 100:.2f}%")
        print(f"📈 Timeframe: {config.TIMEFRAME}")
        print(f"🔢 Max trades simultâneos: {config.MAX_OPEN_TRADES}")
    except Exception as e:
        print(f"❌ Erro nas configurações: {str(e)}")
        exit(1)
