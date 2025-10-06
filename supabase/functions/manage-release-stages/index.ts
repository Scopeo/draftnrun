import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'
import { corsHeaders } from '../_shared/cors.ts'

serve(async (req) => {
  // Handle CORS
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    // Create supabase client with service role key for elevated access
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    
    const supabase = createClient(supabaseUrl, supabaseServiceKey)

    // Get the user from the request headers
    const authorization = req.headers.get('Authorization')
    if (!authorization) {
      return new Response(
        JSON.stringify({ error: 'No authorization header' }),
        { 
          status: 401, 
          headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
        }
      )
    }

    // Get user from JWT token
    const { data: { user }, error: userError } = await supabase.auth.getUser(
      authorization.replace('Bearer ', '')
    )

    if (userError || !user) {
      return new Response(
        JSON.stringify({ error: 'Invalid token' }),
        { 
          status: 401, 
          headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
        }
      )
    }

    // Verify user is super admin
    const { data: isSuperAdmin, error: superAdminError } = await supabase
      .rpc('is_super_admin', { user_id: user.id })

    if (superAdminError || !isSuperAdmin) {
      return new Response(
        JSON.stringify({ error: 'Unauthorized: Super admin access required' }),
        { 
          status: 403, 
          headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
        }
      )
    }

    const method = req.method
    const url = new URL(req.url)
    const pathParts = url.pathname.split('/').filter(Boolean)
    
    switch (method) {
      case 'GET':
        // Get all release stages or specific one
        if (pathParts.length > 2 && pathParts[2]) {
          // Get specific release stage
          const stageId = pathParts[2]
          const { data, error } = await supabase
            .from('release_stages')
            .select('*')
            .eq('id', stageId)
            .single()

          if (error) {
            return new Response(
              JSON.stringify({ error: 'Release stage not found' }),
              { 
                status: 404, 
                headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
              }
            )
          }

          return new Response(
            JSON.stringify(data),
            { 
              status: 200, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        } else {
          // Get all release stages
          const { data, error } = await supabase
            .from('release_stages')
            .select('*')
            .order('display_order', { ascending: true })

          if (error) {
            return new Response(
              JSON.stringify({ error: 'Failed to fetch release stages' }),
              { 
                status: 500, 
                headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
              }
            )
          }

          return new Response(
            JSON.stringify(data),
            { 
              status: 200, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

      case 'POST':
        // Create new release stage
        const newStageData = await req.json()
        
        const { data: newStage, error: createError } = await supabase
          .from('release_stages')
          .insert({
            name: newStageData.name,
            description: newStageData.description,
            display_order: newStageData.display_order || 999,
            is_active: newStageData.is_active !== false,
            created_by: user.id
          })
          .select()
          .single()

        if (createError) {
          return new Response(
            JSON.stringify({ error: 'Failed to create release stage', details: createError.message }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        return new Response(
          JSON.stringify(newStage),
          { 
            status: 201, 
            headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
          }
        )

      case 'PUT':
        // Update existing release stage
        if (!pathParts[2]) {
          return new Response(
            JSON.stringify({ error: 'Release stage ID required' }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        const stageId = pathParts[2]
        const updateData = await req.json()
        
        const { data: updatedStage, error: updateError } = await supabase
          .from('release_stages')
          .update({
            name: updateData.name,
            description: updateData.description,
            display_order: updateData.display_order,
            is_active: updateData.is_active
          })
          .eq('id', stageId)
          .select()
          .single()

        if (updateError) {
          return new Response(
            JSON.stringify({ error: 'Failed to update release stage', details: updateError.message }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        return new Response(
          JSON.stringify(updatedStage),
          { 
            status: 200, 
            headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
          }
        )

      case 'DELETE':
        // Delete release stage (soft delete by setting is_active to false)
        if (!pathParts[2]) {
          return new Response(
            JSON.stringify({ error: 'Release stage ID required' }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        const deleteStageId = pathParts[2]
        
        const { error: deleteError } = await supabase
          .from('release_stages')
          .update({ is_active: false })
          .eq('id', deleteStageId)

        if (deleteError) {
          return new Response(
            JSON.stringify({ error: 'Failed to delete release stage', details: deleteError.message }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        return new Response(
          JSON.stringify({ message: 'Release stage deleted successfully' }),
          { 
            status: 200, 
            headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
          }
        )

      default:
        return new Response(
          JSON.stringify({ error: 'Method not allowed' }),
          { 
            status: 405, 
            headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
          }
        )
    }

  } catch (error) {
    console.error('Error in manage-release-stages function:', error)
    return new Response(
      JSON.stringify({ error: 'Internal server error' }),
      { 
        status: 500, 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
      }
    )
  }
}) 
