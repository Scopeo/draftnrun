import { serve } from "https://deno.land/std@0.177.0/http/server.ts"
import { corsHeaders } from "../_shared/cors.ts"

interface GenerateToolDescriptionRequest {
  componentName: string
  componentDescription?: string
  parameters?: any[]
  userPrompt: string
  currentToolDescription?: {
    name: string
    description: string
    tool_properties: Record<string, any>
    required_tool_properties: string[]
  }
}

interface ToolDescription {
  name: string
  description: string
  tool_properties: Record<string, any>
  required_tool_properties: string[]
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    // Parse request body
    const requestBody: GenerateToolDescriptionRequest = await req.json()
    const { componentName, componentDescription, parameters, userPrompt, currentToolDescription } = requestBody
    
    if (!userPrompt || !componentName) {
      throw new Error('userPrompt and componentName are required')
    }
    
    console.log('Generating tool description for:', { componentName, userPrompt })
    
    // Prepare context for the AI workflow
    const workflowContext = {
      componentName,
      componentDescription: componentDescription || '',
      parameters: parameters || [],
      userRequest: userPrompt,
      currentToolDescription: currentToolDescription || null,
      timestamp: new Date().toISOString()
    }
    
    // Call the actual workflow
    console.log('Calling workflow with context:', workflowContext)
    
    const generatedText = await callWorkflow(workflowContext)
    
    console.log('Generated description text:', generatedText)
    
    return new Response(JSON.stringify({
      success: true,
      data: { description: generatedText }
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 200,
    })
    
  } catch (error) {
    console.error('Generate tool description error:', error)
    return new Response(JSON.stringify({ 
      error: error.message || 'Failed to generate tool description'
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 400,
    })
  }
})

// Function to call the actual workflow
async function callWorkflow(context: any): Promise<any> {
  const apiUrl = Deno.env.get('WORKFLOW_API_URL')
  const apiKey = Deno.env.get('WORKFLOW_API_KEY')
  
  if (!apiUrl || !apiKey) {
    throw new Error('WORKFLOW_API_URL and WORKFLOW_API_KEY environment variables must be set')
  }
  
  // Format request body with messages array as expected by the AI Agent
  const userMessage = `Component: ${context.componentName}
Description: ${context.componentDescription || 'No description provided'}

Current tool description:
- Name: ${context.currentToolDescription?.name || 'Not set'}
- Description: ${context.currentToolDescription?.description || 'Empty'}

User request: ${context.userRequest}

Generate an effective Initial Prompt for this AI agent that will help it understand its role and capabilities. The prompt should:
- Clearly define the AI agent's purpose and role
- Reference available tools and capabilities when relevant
- Provide clear instructions on how to behave
- Include any necessary context or constraints
- Be written as a direct instruction to the AI agent

Write a professional, clear Initial Prompt that the AI agent can follow effectively.`

  const requestBody = {
    messages: [
      {
        role: "user",
        content: userMessage
      }
    ]
  }
  
  console.log('Calling workflow API:', { url: apiUrl, hasKey: !!apiKey })
  
  const response = await fetch(apiUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify(requestBody),
  })
  
  console.log('Response status:', response.status)
  console.log('Response headers:', Object.fromEntries(response.headers.entries()))
  
  if (!response.ok) {
    const errorText = await response.text()
    console.log('Error response body:', errorText)
    throw new Error(`Workflow API error: ${response.status} ${response.statusText} - ${errorText}`)
  }
  
  const result = await response.text()
  console.log('=== WORKFLOW RESPONSE START ===')
  console.log('Raw response type:', typeof result)
  console.log('Raw response length:', result.length)
  console.log('Raw response:', result)
  console.log('=== WORKFLOW RESPONSE END ===')
  
  // Try to parse as JSON first to see the structure
  try {
    const parsed = JSON.parse(result)
    console.log('=== PARSED JSON START ===')
    console.log('Parsed object type:', typeof parsed)
    console.log('Parsed object keys:', Object.keys(parsed))
    console.log('Parsed object:', JSON.stringify(parsed, null, 2))
    console.log('=== PARSED JSON END ===')
    
    // Extract text from various possible formats
    if (typeof parsed === 'string') {
      return parsed.trim()
    } else if (parsed.content) {
      return parsed.content.trim()
    } else if (parsed.message) {
      return parsed.message.trim()
    } else if (parsed.text) {
      return parsed.text.trim()
    } else if (parsed.response) {
      return parsed.response.trim()
    } else {
      return JSON.stringify(parsed)
    }
  } catch (parseError) {
    console.log('Not JSON, treating as plain text')
    return result.trim()
  }
} 
