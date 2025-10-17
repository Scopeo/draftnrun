-- Create agents table for AI agent management
CREATE TABLE IF NOT EXISTS agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  created_by UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  initial_prompt TEXT,
  model_config JSONB DEFAULT '{}',
  tools JSONB DEFAULT '[]',
  is_template BOOLEAN DEFAULT false,
  tags JSONB DEFAULT '[]',
  graph_config JSONB DEFAULT '{}',
  usage_count INTEGER DEFAULT 0,
  last_used_at TIMESTAMPTZ
);

-- Enable RLS
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_agents_organization_id ON agents(organization_id);
CREATE INDEX IF NOT EXISTS idx_agents_created_by ON agents(created_by);
CREATE INDEX IF NOT EXISTS idx_agents_created_at ON agents(created_at);
CREATE INDEX IF NOT EXISTS idx_agents_is_template ON agents(is_template);

-- RLS Policies
-- Users can view agents from their organization
CREATE POLICY "Users can view agents from their organization" ON agents
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.user_id = auth.uid() 
      AND om.org_id = agents.organization_id
    )
  );

-- Users can create agents in their organization
CREATE POLICY "Users can create agents in their organization" ON agents
  FOR INSERT WITH CHECK (
    auth.uid() = created_by AND
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.user_id = auth.uid() 
      AND om.org_id = organization_id
    )
  );

-- Users can update agents they created in their organization
CREATE POLICY "Users can update their agents" ON agents
  FOR UPDATE USING (
    auth.uid() = created_by AND
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.user_id = auth.uid() 
      AND om.org_id = organization_id
    )
  );

-- Users can delete agents they created
CREATE POLICY "Users can delete their agents" ON agents
  FOR DELETE USING (auth.uid() = created_by);

-- Grant permissions
GRANT ALL ON agents TO authenticated;
