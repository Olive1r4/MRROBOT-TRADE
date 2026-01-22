-- Fix RLS policies for wallet_history table
-- This allows the bot to insert wallet history records

-- Drop existing restrictive policies if any
DROP POLICY IF EXISTS "Enable read access for all users" ON wallet_history;
DROP POLICY IF EXISTS "Enable insert for authenticated users only" ON wallet_history;

-- Create permissive policies for service role and anon
CREATE POLICY "Enable read access for all users"
ON wallet_history FOR SELECT
USING (true);

CREATE POLICY "Enable insert for all users"
ON wallet_history FOR INSERT
WITH CHECK (true);

CREATE POLICY "Enable update for all users"
ON wallet_history FOR UPDATE
USING (true);

-- Verify RLS is enabled
ALTER TABLE wallet_history ENABLE ROW LEVEL SECURITY;
