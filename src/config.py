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
    TARGET_PROFIT: float = Field(default=0.006, description="Lucro alvo (0.6%)")
    TRADING_FEE: float = Field(default=0.0004, description="Taxa de trading (0.04%)")
    
    # STOP LOSS POR TRADE (CRÍTICO!)
    # Risk:Reward deve ser próximo de 1:1 ou 1:1.5
    # Com target de 0.6%, stop deve ser 0.6-0.9%
    STOP_LOSS_PERCENTAGE: float = Field(default=0.008, description="Stop loss por trade (0.8%)")
    MAX_LOSS_PER_TRADE: float = Field(default=0.009, description="Perda máxima por trade (0.9%)")
    
    # ALAVANCAGEM (conservadora para scalping)
    # Iniciantes: 3x-5x | Avançados: até 10x
    DEFAULT_LEVERAGE: int = Field(default=5, description="Alavancagem padrão (5x moderado)")
    MAX_LEVERAGE: int = Field(default=10, description="Alavancagem máxima permitida")
    
    DEFAULT_POSITION_SIZE: float = Field(default=100.00, description="Tamanho padrão da posição em USDT")
    
    # ============================================
    # INDICADORES TÉCNICOS (OTIMIZADOS PARA 1 MINUTO)
    # ============================================
    RSI_PERIOD: int = Field(default=10, description="Período do RSI (reduzido para 1min)")
    RSI_OVERSOLD: float = Field(default=25, description="Nível de sobrevenda do RSI (mais conservador)")
    RSI_OVERBOUGHT: float = Field(default=75, description="Nível de sobrecompra do RSI")
    
    BB_PERIOD: int = Field(default=15, description="Período das Bandas de Bollinger (mais dinâmico)")
    BB_STD_DEV: float = Field(default=2.0, description="Desvio padrão das Bollinger")
    
    EMA_PERIOD: int = Field(default=100, description="Período da EMA (ajustado para 1min)")
    
    ATR_PERIOD: int = Field(default=10, description="Período do ATR (mais responsivo)")
    # ATR usado para stop loss dinâmico baseado em volatilidade
    # Objetivo: stop entre 0.3-0.9% do preço de entrada
    ATR_MULTIPLIER: float = Field(default=1.5, description="Multiplicador do ATR para stop loss dinâmico")
    USE_ATR_STOP: bool = Field(default=True, description="Usar ATR para calcular stop loss (recomendado)")
    USE_FIXED_STOP: bool = Field(default=False, description="Usar stop loss fixo de STOP_LOSS_PERCENTAGE")
    
    TIMEFRAME: str = Field(default="1m", description="Timeframe para análise (SCALPING)")
    
    # ============================================
    # GUARDRAILS DE SEGURANÇA (REFORÇADOS PARA 1 MINUTO)
    # ============================================
    DAILY_STOP_LOSS: float = Field(default=0.05, description="Stop loss diário (5%)")
    MAX_OPEN_TRADES: int = Field(default=1, description="Máximo de trades abertos (1 para evitar overtrading)")
    TRADE_COOLDOWN_SECONDS: int = Field(default=180, description="Cooldown entre trades (3min)")
    MAX_ORDERS_PER_MINUTE: int = Field(default=3, description="Rate limit de ordens (mais conservador)")
    
    # ============================================
    # SCANNER DE MERCADO
    # ============================================
    ENABLE_SCANNER: bool = Field(default=True, description="Habilitar scanner automático de mercado")
    SCANNER_CHECK_INTERVAL: int = Field(default=30, description="Intervalo entre verificações do scanner (segundos)")
    
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
