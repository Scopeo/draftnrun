-- Create super_admins table for secure super admin management
CREATE TABLE IF NOT EXISTS super_admins (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  created_by UUID REFERENCES auth.users(id),
  notes TEXT -- Optional notes about why this user is a super admin
);

-- Create release_stages table
CREATE TABLE IF NOT EXISTS release_stages (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  display_order INTEGER DEFAULT 0,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_by UUID REFERENCES auth.users(id)
);

-- Create organization_release_stages junction table
CREATE TABLE IF NOT EXISTS organization_release_stages (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  release_stage_id UUID NOT NULL REFERENCES release_stages(id) ON DELETE CASCADE,
  assigned_at TIMESTAMPTZ DEFAULT NOW(),
  assigned_by UUID REFERENCES auth.users(id),
  UNIQUE(org_id, release_stage_id)
);

-- Enable RLS
ALTER TABLE super_admins ENABLE ROW LEVEL SECURITY;
ALTER TABLE release_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_release_stages ENABLE ROW LEVEL SECURITY;

-- Create helper function to check if user is super admin
CREATE OR REPLACE FUNCTION is_super_admin(user_id UUID DEFAULT auth.uid())
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM super_admins 
    WHERE super_admins.user_id = $1
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RLS Policies for super_admins table
-- Only existing super admins can read the super_admins table
CREATE POLICY "Super admins can read super admins table" ON super_admins
  FOR SELECT USING (is_super_admin());

-- Only existing super admins can manage super admin assignments
CREATE POLICY "Super admins can manage super admins" ON super_admins
  FOR ALL USING (is_super_admin());

-- Service role can always manage (for initial setup)
CREATE POLICY "Service role can manage super admins" ON super_admins
  FOR ALL USING (auth.role() = 'service_role');

-- RLS Policies for release_stages
-- Super admins can manage all release stages
CREATE POLICY "Super admins can manage release stages" ON release_stages
  FOR ALL USING (is_super_admin());

-- All authenticated users can read active release stages (for checking feature access)
CREATE POLICY "Authenticated users can read active release stages" ON release_stages
  FOR SELECT USING (auth.role() = 'authenticated' AND is_active = true);

-- RLS Policies for organization_release_stages  
-- Super admins can manage all org release stage assignments
CREATE POLICY "Super admins can manage org release stages" ON organization_release_stages
  FOR ALL USING (is_super_admin());

-- Organization members can read their org's release stage assignments
CREATE POLICY "Org members can read their release stages" ON organization_release_stages
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.user_id = auth.uid() 
      AND om.org_id = organization_release_stages.org_id
    )
  );

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_super_admins_user_id ON super_admins(user_id);
CREATE INDEX IF NOT EXISTS idx_release_stages_name ON release_stages(name);
CREATE INDEX IF NOT EXISTS idx_release_stages_display_order ON release_stages(display_order);
CREATE INDEX IF NOT EXISTS idx_release_stages_active ON release_stages(is_active);
CREATE INDEX IF NOT EXISTS idx_organization_release_stages_org_id ON organization_release_stages(org_id);
CREATE INDEX IF NOT EXISTS idx_organization_release_stages_release_stage_id ON organization_release_stages(release_stage_id);

-- Create update trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_release_stages_updated_at 
  BEFORE UPDATE ON release_stages 
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default release stages with correct names
INSERT INTO release_stages (name, description, display_order) VALUES
  ('internal', 'Internal team members - access to all features including experimental ones', 0),
  ('early_access', 'Early access users - beta features and previews', 1),
  ('beta', 'Beta users - stable beta features', 2),
  ('public', 'General public - stable features only', 3)
ON CONFLICT (name) DO NOTHING;

-- Create a view for easy access to organization release stages with names
CREATE OR REPLACE VIEW organization_release_stages_view AS
SELECT 
  ors.org_id,
  ors.release_stage_id,
  rs.name as release_stage_name,
  rs.description as release_stage_description,
  rs.display_order,
  ors.assigned_at,
  ors.assigned_by
FROM organization_release_stages ors
JOIN release_stages rs ON ors.release_stage_id = rs.id
WHERE rs.is_active = true;

-- Grant access to the view
GRANT SELECT ON organization_release_stages_view TO authenticated; 
