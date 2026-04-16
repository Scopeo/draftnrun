-- Add test agent from ada-staging project to agents table
INSERT INTO agents (
  id,
  name,
  description,
  organization_id,
  created_by,
  created_at,
  updated_at,
  initial_prompt,
  model_config,
  tools,
  is_template,
  tags,
  graph_config,
  usage_count,
  last_used_at,
  parameters
) VALUES (
  '3d23be83-4927-4d58-a373-6db6b60a7c5d',
  'Ada Staging Test Agent',
  'Test agent imported from ada-staging.scopeo.studio for sandbox testing',
  'your-org-id', -- Replace with your actual organization ID
  'your-user-id', -- Replace with your actual user ID
  NOW(),
  NOW(),
  'You are a helpful AI assistant from the Ada staging environment.',
  '{"model": "gpt-4", "temperature": 0.7, "max_tokens": 2000}',
  '[]', -- Empty tools array for now
  false,
  '["test", "staging", "ada"]',
  '{
    "project_id": "3d23be83-4927-4d58-a373-6db6b60a7c5d",
    "source_url": "https://ada-staging.scopeo.studio/projects/3d23be83-4927-4d58-a373-6db6b60a7c5d/draft/chat",
    "runner_type": "graph",
    "version": "draft"
  }',
  0,
  NOW(),
  jsonb_build_array(
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
      'value', 'You are a helpful AI assistant from the Ada staging environment. You can help users with various tasks and provide information.',
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
      'value', 15,
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
);

-- Verification query to check the inserted agent
SELECT id, name, description, parameters->1->>'value' as initial_prompt_value
FROM agents
WHERE id = '3d23be83-4927-4d58-a373-6db6b60a7c5d';