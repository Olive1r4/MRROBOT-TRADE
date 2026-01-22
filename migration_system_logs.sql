-- Migration: Add system_logs table for error tracking
CREATE TABLE IF NOT EXISTS system_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    level TEXT NOT NULL,
    module TEXT,
    message TEXT NOT NULL,
    stack_trace TEXT,
    mode TEXT,
    metadata JSONB
);

-- Index for faster ordering
CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs (created_at DESC);

-- Enable RLS
ALTER TABLE system_logs ENABLE ROW LEVEL SECURITY;

-- Policies
CREATE POLICY "Allow service role full access" ON system_logs FOR ALL USING (true);
CREATE POLICY "Allow anonymous insert" ON system_logs FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow read access for all" ON system_logs FOR SELECT USING (true);
