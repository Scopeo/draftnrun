CREATE DATABASE ada_traces;

\c ada_traces;
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Schedule cleanup job for span_messages from spans older than 90 days
SELECT cron.schedule(
    'cleanup-old-spans',
    '0 2 * * *',  -- 2 AM UTC daily
    $$
    DELETE FROM span_messages
    WHERE span_id IN (
        SELECT s.span_id FROM spans s
        WHERE s.start_time < NOW() - INTERVAL '90 days'
    );
    $$
);
