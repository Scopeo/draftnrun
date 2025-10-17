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
        // Get organization release stage assignments
        if (pathParts[2] === 'org' && pathParts[3]) {
          // Get release stages for specific organization
          const orgId = pathParts[3]
          const { data, error } = await supabase
            .from('organization_release_stages_view')
            .select('*')
            .eq('org_id', orgId)

          if (error) {
            return new Response(
              JSON.stringify({ error: 'Failed to fetch organization release stages' }),
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
        } else {
          // Get all organization release stage assignments
          const { data, error } = await supabase
            .from('organization_release_stages_view')
            .select(`
              *,
              organizations!inner(id, name)
            `)
            .order('display_order', { ascending: true })

          if (error) {
            return new Response(
              JSON.stringify({ error: 'Failed to fetch organization release stages' }),
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
        // Assign organization to release stage
        const assignmentData = await req.json()
        
        if (!assignmentData.org_id || !assignmentData.release_stage_id) {
          return new Response(
            JSON.stringify({ error: 'Organization ID and Release Stage ID are required' }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        // First, remove any existing assignment for this org (one stage per org)
        await supabase
          .from('organization_release_stages')
          .delete()
          .eq('org_id', assignmentData.org_id)

        // Create new assignment
        const { data: newAssignment, error: createError } = await supabase
          .from('organization_release_stages')
          .insert({
            org_id: assignmentData.org_id,
            release_stage_id: assignmentData.release_stage_id,
            assigned_by: user.id
          })
          .select(`
            *,
            release_stages(name, description, display_order)
          `)
          .single()

        if (createError) {
          return new Response(
            JSON.stringify({ error: 'Failed to assign organization to release stage', details: createError.message }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        return new Response(
          JSON.stringify(newAssignment),
          { 
            status: 201, 
            headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
          }
        )

      case 'DELETE':
        // Remove organization from release stage
        if (!pathParts[2] || !pathParts[3]) {
          return new Response(
            JSON.stringify({ error: 'Organization ID is required' }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        const orgIdToRemove = pathParts[3]
        
        const { error: deleteError } = await supabase
          .from('organization_release_stages')
          .delete()
          .eq('org_id', orgIdToRemove)

        if (deleteError) {
          return new Response(
            JSON.stringify({ error: 'Failed to remove organization from release stage', details: deleteError.message }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        return new Response(
          JSON.stringify({ message: 'Organization removed from release stage successfully' }),
          { 
            status: 200, 
            headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
          }
        )

      case 'PUT':
        // Update organization release stage assignment
        if (!pathParts[2] || !pathParts[3]) {
          return new Response(
            JSON.stringify({ error: 'Organization ID is required' }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        const orgIdToUpdate = pathParts[3]
        const updateData = await req.json()

        if (!updateData.release_stage_id) {
          return new Response(
            JSON.stringify({ error: 'Release Stage ID is required' }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        // Update the assignment
        const { data: updatedAssignment, error: updateError } = await supabase
          .from('organization_release_stages')
          .update({
            release_stage_id: updateData.release_stage_id,
            assigned_by: user.id,
            assigned_at: new Date().toISOString()
          })
          .eq('org_id', orgIdToUpdate)
          .select(`
            *,
            release_stages(name, description, display_order)
          `)
          .single()

        if (updateError) {
          return new Response(
            JSON.stringify({ error: 'Failed to update organization release stage', details: updateError.message }),
            { 
              status: 400, 
              headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
            }
          )
        }

        return new Response(
          JSON.stringify(updatedAssignment),
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
    console.error('Error in manage-org-release-stages function:', error)
    return new Response(
      JSON.stringify({ error: 'Internal server error' }),
      { 
        status: 500, 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
      }
    )
  }
}) 
