CREATE DATABASE ada_traces;

-- Ensure pg_cron exists in the 'postgres' database (where the worker runs)
\c postgres;
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Schedule cleanup job (runs in ada_backend) for span_messages older than 90 days in traces schema
-- Note: requires pg_cron >= 1.6 for schedule_in_database signature (jobname, schedule, command, database)
SELECT cron.schedule_in_database(
  'cleanup-old-spans',
  '0 2 * * *',  -- 2 AM UTC daily
  $q$
  DELETE FROM traces.span_messages
  WHERE span_id IN (
      SELECT s.span_id FROM traces.spans s
      WHERE s.start_time < NOW() - INTERVAL '90 days'
  );
  $q$,
  'ada_backend'
)
WHERE NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'cleanup-old-spans');
