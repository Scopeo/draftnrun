-- Chat History Schema for Agent Playground
-- This schema stores chat conversations between users and AI agents with auto-delete after 30 days

-- Create the chat_history table
CREATE TABLE IF NOT EXISTS chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    agent_id VARCHAR(255) NOT NULL,
    chat_id UUID NOT NULL DEFAULT gen_random_uuid(),
    title VARCHAR(255), -- Optional chat title (first user message or custom name)
    messages JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Indexes for performance
    CONSTRAINT chat_history_messages_check CHECK (jsonb_typeof(messages) = 'array')
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_agent_id ON chat_history(agent_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_chat_id ON chat_history(chat_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON chat_history(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_history_user_agent ON chat_history(user_id, agent_id);

-- Create a function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_chat_history_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update updated_at
CREATE TRIGGER update_chat_history_updated_at_trigger
    BEFORE UPDATE ON chat_history
    FOR EACH ROW
    EXECUTE FUNCTION update_chat_history_updated_at();

-- Auto-delete policy: Remove chats older than 30 days
-- This can be done with a scheduled job or RLS policy
-- Option 1: Using a function that can be called by cron
CREATE OR REPLACE FUNCTION cleanup_old_chat_history()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM chat_history
    WHERE created_at < NOW() - INTERVAL '30 days';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    -- Log cleanup for debugging
    INSERT INTO postgres_log (level, message, created_at)
    VALUES ('info', format('Cleaned up %s old chat history records', deleted_count), NOW())
    ON CONFLICT DO NOTHING; -- Ignore if log table doesn't exist

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Row Level Security (RLS) policies
ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;

-- Users can only see their own chat history
CREATE POLICY "Users can view their own chat history" ON chat_history
    FOR SELECT USING (auth.uid() = user_id);

-- Users can insert their own chat history
CREATE POLICY "Users can insert their own chat history" ON chat_history
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Users can update their own chat history
CREATE POLICY "Users can update their own chat history" ON chat_history
    FOR UPDATE USING (auth.uid() = user_id);

-- Users can delete their own chat history
CREATE POLICY "Users can delete their own chat history" ON chat_history
    FOR DELETE USING (auth.uid() = user_id);

-- Create a view for easier querying with user info
CREATE OR REPLACE VIEW chat_history_with_user AS
SELECT
    ch.*,
    u.email as user_email
FROM chat_history ch
JOIN auth.users u ON ch.user_id = u.id;

-- Grant necessary permissions
GRANT ALL ON chat_history TO authenticated;
GRANT SELECT ON chat_history_with_user TO authenticated;

-- Example message structure in JSONB:
-- [
--   {
--     "id": "msg_123",
--     "role": "user",
--     "content": "Hello, how are you?",
--     "timestamp": "2024-01-15T10:30:00Z"
--   },
--   {
--     "id": "msg_124",
--     "role": "assistant",
--     "content": "I'm doing well, thank you! How can I help you today?",
--     "timestamp": "2024-01-15T10:30:02Z",
--     "artifacts": {
--       "sources": [...],
--       "images": [...]
--     }
--   }
-- ]

-- Optional: Create a function to get chat history for a specific user and agent
CREATE OR REPLACE FUNCTION get_user_chat_history(p_agent_id VARCHAR DEFAULT NULL, p_limit INTEGER DEFAULT 50)
RETURNS TABLE (
    id UUID,
    agent_id VARCHAR,
    chat_id UUID,
    title VARCHAR,
    message_count INTEGER,
    last_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ch.id,
        ch.agent_id,
        ch.chat_id,
        ch.title,
        jsonb_array_length(ch.messages) as message_count,
        ch.updated_at as last_message_at,
        ch.created_at
    FROM chat_history ch
    WHERE ch.user_id = auth.uid()
        AND (p_agent_id IS NULL OR ch.agent_id = p_agent_id)
    ORDER BY ch.updated_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant execute permission on the function
GRANT EXECUTE ON FUNCTION get_user_chat_history TO authenticated;

-- Optional: Function to get a specific chat with all messages
CREATE OR REPLACE FUNCTION get_chat_messages(p_chat_id UUID)
RETURNS TABLE (
    id UUID,
    agent_id VARCHAR,
    chat_id UUID,
    title VARCHAR,
    messages JSONB,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ch.id,
        ch.agent_id,
        ch.chat_id,
        ch.title,
        ch.messages,
        ch.created_at,
        ch.updated_at
    FROM chat_history ch
    WHERE ch.user_id = auth.uid()
        AND ch.chat_id = p_chat_id
    LIMIT 1;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION get_chat_messages TO authenticated;

COMMENT ON TABLE chat_history IS 'Stores chat conversations between users and AI agents';
COMMENT ON COLUMN chat_history.messages IS 'JSONB array of chat messages with id, role, content, timestamp, and optional artifacts';
COMMENT ON COLUMN chat_history.chat_id IS 'Unique identifier for a conversation thread';
COMMENT ON COLUMN chat_history.title IS 'Optional human-readable title for the chat (auto-generated from first message)';
