-- Migration: Add parameters JSONB column to agents table and populate with existing data
-- Run this in your Supabase SQL Editor or via psql

-- Step 1: Add parameters column as JSONB
ALTER TABLE agents ADD COLUMN IF NOT EXISTS parameters JSONB DEFAULT '[]'::jsonb;

-- Step 2: Populate parameters column with the 5-parameter structure for existing agents
UPDATE agents
SET parameters = jsonb_build_array(
  jsonb_build_object(
    'name', 'api_key',
    'type', 'string',
    'description', 'API key for external service integration',
    'default', '',
    'value', '',
    'required', false,
    'is_advanced', true,
    'ui_component', 'TextField',
    'ui_component_properties', jsonb_build_object(
      'label', 'API Key',
      'type', 'password',
      'placeholder', 'Enter your API key'
    )
  ),
  jsonb_build_object(
    'name', 'initial_prompt',
    'type', 'string',
    'description', 'Instructions for the agent behavior and role',
    'default', 'You are a helpful AI assistant.',
    'value', COALESCE(initial_prompt, 'You are a helpful AI assistant.'),
    'required', true,
    'is_advanced', false,
    'ui_component', 'Textarea',
    'ui_component_properties', jsonb_build_object(
      'label', 'Instructions for the agent',
      'rows', 8,
      'placeholder', 'You are a helpful AI assistant...'
    )
  ),
  jsonb_build_object(
    'name', 'run_tools_in_parallel',
    'type', 'boolean',
    'description', 'Whether to run multiple tools simultaneously for faster execution',
    'default', true,
    'value', true,
    'required', false,
    'is_advanced', true,
    'ui_component', 'Checkbox',
    'ui_component_properties', jsonb_build_object(
      'label', 'Run Tools In Parallel'
    )
  ),
  jsonb_build_object(
    'name', 'max_iterations',
    'type', 'integer',
    'description', 'Maximum number of iterations the agent can perform',
    'default', 10,
    'value', 10,
    'required', false,
    'is_advanced', true,
    'ui_component', 'Slider',
    'ui_component_properties', jsonb_build_object(
      'label', 'Max Iterations',
      'min', 1,
      'max', 50,
      'step', 1,
      'marks', true
    )
  ),
  jsonb_build_object(
    'name', 'completion_model',
    'type', 'string',
    'description', 'The AI model to use for generating responses',
    'default', 'gpt-4',
    'value', 'gpt-4',
    'required', true,
    'is_advanced', false,
    'ui_component', 'Select',
    'ui_component_properties', jsonb_build_object(
      'label', 'Completion Model',
      'options', jsonb_build_array(
        jsonb_build_object('label', 'GPT-4', 'value', 'gpt-4'),
        jsonb_build_object('label', 'GPT-3.5 Turbo', 'value', 'gpt-3.5-turbo'),
        jsonb_build_object('label', 'Claude-3-Opus', 'value', 'claude-3-opus'),
        jsonb_build_object('label', 'Claude-3-Sonnet', 'value', 'claude-3-sonnet')
      )
    )
  )
)
WHERE parameters = '[]'::jsonb OR parameters IS NULL;

-- Step 3: system_prompt column doesn't exist - skipping backward compatibility update

-- Step 4: Create index on parameters for better query performance
CREATE INDEX IF NOT EXISTS idx_agents_parameters ON agents USING gin (parameters);

-- Verification queries (uncomment to check results):
-- SELECT id, name, parameters->>1 as initial_prompt_param FROM agents LIMIT 3;
-- SELECT id, name, jsonb_array_length(parameters) as param_count FROM agents;
