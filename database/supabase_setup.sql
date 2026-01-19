-- ============================================
-- SUPABASE SETUP - SCALPING BOT
-- ============================================
-- Este script cria todas as tabelas necessárias para o bot de scalping
-- Execute no SQL Editor do Supabase: https://app.supabase.com/project/_/sql

-- ============================================
-- 1. TABELA: coins_config
-- Gerencia quais moedas estão ativas e suas configurações
-- ============================================
CREATE TABLE IF NOT EXISTS coins_config (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT true,
    min_pnl DECIMAL(10, 6) DEFAULT 0.006, -- 0.6% de lucro mínimo
    max_position_size DECIMAL(20, 8) DEFAULT 100.00, -- Tamanho máximo da posição em USDT
    leverage INTEGER DEFAULT 10, -- Alavancagem padrão
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índices para otimização de consultas
CREATE INDEX idx_coins_config_symbol ON coins_config(symbol);
CREATE INDEX idx_coins_config_active ON coins_config(is_active);

-- Inserir algumas moedas populares como exemplo
-- Alavancagem conservadora: 3x (iniciantes) a 5x (avançados)
INSERT INTO coins_config (symbol, is_active, min_pnl, max_position_size, leverage) VALUES
    ('BTCUSDT', true, 0.006, 500.00, 3),
    ('ETHUSDT', true, 0.006, 300.00, 3),
    ('BNBUSDT', true, 0.006, 200.00, 3),
    ('SOLUSDT', true, 0.006, 150.00, 3),
    ('ADAUSDT', false, 0.006, 100.00, 3)
ON CONFLICT (symbol) DO NOTHING;

-- ============================================
-- 2. TABELA: trades_history
-- Registra todas as operações executadas pelo bot
-- ============================================
CREATE TABLE IF NOT EXISTS trades_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL, -- 'buy' ou 'sell'
    entry_price DECIMAL(20, 8) NOT NULL,
    exit_price DECIMAL(20, 8),
    quantity DECIMAL(20, 8) NOT NULL,
    leverage INTEGER DEFAULT 10,
    target_price DECIMAL(20, 8),
    stop_loss_price DECIMAL(20, 8),
    pnl DECIMAL(20, 8) DEFAULT 0.00,
    pnl_percentage DECIMAL(10, 6) DEFAULT 0.00,
    status VARCHAR(20) DEFAULT 'open', -- 'open', 'closed', 'stopped', 'cancelled'
    entry_reason TEXT, -- Ex: "RSI < 30 e preço abaixo da banda inferior"
    exit_reason TEXT, -- Ex: "Take profit atingido"
    order_id_entry VARCHAR(100),
    order_id_exit VARCHAR(100),
    mode VARCHAR(10) NOT NULL, -- 'MOCK' ou 'PROD'
    entry_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    exit_time TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índices para otimização de consultas
CREATE INDEX idx_trades_symbol ON trades_history(symbol);
CREATE INDEX idx_trades_status ON trades_history(status);
CREATE INDEX idx_trades_entry_time ON trades_history(entry_time);
CREATE INDEX idx_trades_mode ON trades_history(mode);

-- ============================================
-- 3. TABELA: bot_logs
-- Registra eventos importantes e erros do bot
-- ============================================
CREATE TABLE IF NOT EXISTS bot_logs (
    id SERIAL PRIMARY KEY,
    level VARCHAR(20) NOT NULL, -- 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    message TEXT NOT NULL,
    details JSONB, -- Dados adicionais em formato JSON
    symbol VARCHAR(20),
    trade_id INTEGER REFERENCES trades_history(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índices para otimização de consultas
CREATE INDEX idx_logs_level ON bot_logs(level);
CREATE INDEX idx_logs_created_at ON bot_logs(created_at);
CREATE INDEX idx_logs_symbol ON bot_logs(symbol);

-- ============================================
-- 4. TABELA: daily_pnl
-- Rastreia o PnL diário para circuit breaker
-- ============================================
CREATE TABLE IF NOT EXISTS daily_pnl (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL UNIQUE,
    total_pnl DECIMAL(20, 8) DEFAULT 0.00,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    is_circuit_breaker_active BOOLEAN DEFAULT false,
    circuit_breaker_activated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índice para otimização de consultas
CREATE INDEX idx_daily_pnl_date ON daily_pnl(trade_date);

-- ============================================
-- 5. TABELA: rate_limiter
-- Controla o rate limiting das requisições
-- ============================================
CREATE TABLE IF NOT EXISTS rate_limiter (
    id SERIAL PRIMARY KEY,
    minute_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    request_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índice para otimização de consultas
CREATE INDEX idx_rate_limiter_timestamp ON rate_limiter(minute_timestamp);

-- ============================================
-- 6. TABELA: trade_cooldown
-- Gerencia o cooldown entre trades da mesma moeda
-- ============================================
CREATE TABLE IF NOT EXISTS trade_cooldown (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    last_trade_time TIMESTAMP WITH TIME ZONE NOT NULL,
    cooldown_until TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índice para otimização de consultas
CREATE INDEX idx_cooldown_symbol ON trade_cooldown(symbol);
CREATE INDEX idx_cooldown_until ON trade_cooldown(cooldown_until);

-- ============================================
-- FUNCTIONS E TRIGGERS
-- ============================================

-- Function para atualizar o campo updated_at automaticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para coins_config
CREATE TRIGGER update_coins_config_updated_at
    BEFORE UPDATE ON coins_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger para daily_pnl
CREATE TRIGGER update_daily_pnl_updated_at
    BEFORE UPDATE ON daily_pnl
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- VIEWS ÚTEIS
-- ============================================

-- View para estatísticas diárias
CREATE OR REPLACE VIEW daily_stats AS
SELECT 
    trade_date,
    total_pnl,
    total_trades,
    winning_trades,
    losing_trades,
    CASE 
        WHEN total_trades > 0 THEN ROUND((winning_trades::DECIMAL / total_trades::DECIMAL) * 100, 2)
        ELSE 0 
    END as win_rate_percentage,
    is_circuit_breaker_active
FROM daily_pnl
ORDER BY trade_date DESC;

-- View para trades abertos
CREATE OR REPLACE VIEW open_trades AS
SELECT 
    id,
    symbol,
    entry_price,
    quantity,
    leverage,
    target_price,
    stop_loss_price,
    entry_reason,
    mode,
    entry_time,
    EXTRACT(EPOCH FROM (NOW() - entry_time))/60 as minutes_open
FROM trades_history
WHERE status = 'open'
ORDER BY entry_time DESC;

-- View para performance por moeda
CREATE OR REPLACE VIEW performance_by_symbol AS
SELECT 
    symbol,
    COUNT(*) as total_trades,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
    ROUND(AVG(pnl_percentage), 4) as avg_pnl_percentage,
    ROUND(SUM(pnl), 4) as total_pnl
FROM trades_history
WHERE status = 'closed'
GROUP BY symbol
ORDER BY total_pnl DESC;

-- ============================================
-- LIMPEZA AUTOMÁTICA (OPCIONAL)
-- ============================================

-- Function para limpar logs antigos (> 30 dias)
CREATE OR REPLACE FUNCTION cleanup_old_logs()
RETURNS void AS $$
BEGIN
    DELETE FROM bot_logs
    WHERE created_at < NOW() - INTERVAL '30 days';
    
    DELETE FROM rate_limiter
    WHERE created_at < NOW() - INTERVAL '7 days';
END;
$$ LANGUAGE plpgsql;

-- Para executar a limpeza manualmente:
-- SELECT cleanup_old_logs();

-- ============================================
-- PERMISSÕES (OPCIONAL - AJUSTAR CONFORME NECESSÁRIO)
-- ============================================

-- Se você criou um usuário específico para o bot, descomente e ajuste:
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO scalping_bot_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO scalping_bot_user;

-- ============================================
-- FIM DO SCRIPT
-- ============================================

-- Para verificar se tudo foi criado corretamente:
SELECT 
    table_name, 
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'public' 
    AND table_type = 'BASE TABLE'
    AND table_name IN ('coins_config', 'trades_history', 'bot_logs', 'daily_pnl', 'rate_limiter', 'trade_cooldown')
ORDER BY table_name;
