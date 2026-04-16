-- Create help_requests table without RLS
CREATE TABLE help_requests (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  project_id TEXT,
  title TEXT NOT NULL,
  issue_description TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  status TEXT DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved')),
  admin_notes TEXT
);

-- Create index for performance
CREATE INDEX idx_help_requests_user_id ON help_requests(user_id);
CREATE INDEX idx_help_requests_created_at ON help_requests(created_at); 
