-- Add user whitelist table (easily removable when going public)
CREATE TABLE IF NOT EXISTS user_whitelist (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  notes TEXT -- Optional notes about why this email was whitelisted
);

-- Enable RLS
ALTER TABLE user_whitelist ENABLE ROW LEVEL SECURITY;

-- Only authenticated users can read (for checking), but in practice only functions will use this
CREATE POLICY "Allow authenticated users to read whitelist" ON user_whitelist
  FOR SELECT USING (auth.role() = 'authenticated');

-- Insert some initial whitelist entries (replace with actual emails you want to allow)
INSERT INTO user_whitelist (email, notes) VALUES 
  ('test@example.com', 'Test user'),
  ('admin@yourdomain.com', 'Admin user')
ON CONFLICT (email) DO NOTHING; 
