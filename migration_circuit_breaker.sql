-- Migration: Add circuit_breaker table for risk management
CREATE TABLE IF NOT EXISTS circuit_breaker (
    id INTEGER PRIMARY KEY DEFAULT 1,
    is_system_active BOOLEAN DEFAULT true,
    max_daily_loss_percent DECIMAL DEFAULT 0.10,
    cooldown_minutes INTEGER DEFAULT 60,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    CONSTRAINT single_row CHECK (id = 1)
);

-- Habilitar RLS (Segurança)
ALTER TABLE circuit_breaker ENABLE ROW LEVEL SECURITY;

-- Política: O bot (e você) podem ler e editar livremente
CREATE POLICY "Enable read access for all users" ON circuit_breaker FOR SELECT USING (true);
CREATE POLICY "Enable insert/update for service_role" ON circuit_breaker FOR ALL USING (true);

-- Inserir configuração inicial
INSERT INTO circuit_breaker (id, is_system_active, max_daily_loss_percent, cooldown_minutes)
VALUES (1, true, 0.10, 60)
ON CONFLICT (id) DO NOTHING;
