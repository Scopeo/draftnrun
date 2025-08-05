-- Table to store pending organization creation data for users awaiting email verification
CREATE TABLE IF NOT EXISTS pending_user_orgs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  username TEXT NOT NULL,
  email TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  processed BOOLEAN DEFAULT FALSE,
  processed_at TIMESTAMPTZ,
  org_id UUID REFERENCES organizations(id) -- Set after org is created
);

-- Enable RLS
ALTER TABLE pending_user_orgs ENABLE ROW LEVEL SECURITY;

-- Allow functions to manage pending org data
CREATE POLICY "Allow service role to manage pending orgs" ON pending_user_orgs
  FOR ALL USING (auth.role() = 'service_role');

-- Index for efficient lookup
CREATE INDEX IF NOT EXISTS idx_pending_user_orgs_user_id ON pending_user_orgs(user_id);
CREATE INDEX IF NOT EXISTS idx_pending_user_orgs_processed ON pending_user_orgs(processed); 
