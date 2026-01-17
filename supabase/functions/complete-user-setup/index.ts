import { serve } from "https://deno.land/std@0.177.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.7.1"
import { corsHeaders } from "../_shared/cors.ts"

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    let requestBody = {}
    try {
      requestBody = await req.json()
    } catch (jsonError) {
      console.log('No JSON body provided')
    }
    
    const { access_token, refresh_token, user_id } = requestBody
    console.log('Request body:', { 
      hasAccessToken: !!access_token, 
      hasRefreshToken: !!refresh_token, 
      user_id 
    })
    
    const supabaseAdmin = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
    )
    
    let user = null
    let session = null
    
    if (access_token && refresh_token) {
      console.log('Verifying user with tokens...')
      
      // Use the tokens to get the user and create a session
      const supabaseUser = createClient(
        Deno.env.get('SUPABASE_URL') ?? '',
        Deno.env.get('SUPABASE_ANON_KEY') ?? ''
      )
      
      const { data: sessionData, error: sessionError } = await supabaseUser.auth.setSession({
        access_token,
        refresh_token
      })
      
      if (sessionError || !sessionData.session?.user) {
        console.error('Session verification failed:', sessionError)
        throw new Error('Invalid verification tokens: ' + (sessionError?.message || 'Unknown error'))
      }
      
      user = sessionData.session.user
      session = sessionData.session
      console.log('Successfully verified user via tokens:', user.email)
      
    } else if (user_id) {
      console.log('Getting user by ID:', user_id)
      // Fallback: get user by ID
      const { data: userData, error: userError } = await supabaseAdmin.auth.admin.getUserById(user_id)
      if (userError || !userData.user) {
        console.error('Failed to get user by ID:', userError)
        throw new Error('User not found: ' + (userError?.message || 'Unknown error'))
      }
      user = userData.user
      console.log('Successfully got user by ID:', user.email)
      
    } else {
      throw new Error('No verification tokens or user_id provided')
    }
    
    // Check if user already has organizations
    const { data: existingMemberships, error: membershipError } = await supabaseAdmin
      .from('organization_members')
      .select('org_id')
      .eq('user_id', user.id)
    
    if (membershipError) {
      throw membershipError
    }
    
    // If user already has organizations, they don't need setup
    if (existingMemberships && existingMemberships.length > 0) {
      return new Response(JSON.stringify({ 
        success: true,
        message: 'User already has organizations',
        alreadySetup: true
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 200,
      })
    }
    
    // Look for pending org data
    const { data: pendingOrg, error: pendingError } = await supabaseAdmin
      .from('pending_user_orgs')
      .select('*')
      .eq('user_id', user.id)
      .eq('processed', false)
      .single()
    
    let username = user.user_metadata?.username || user.email?.split('@')[0] || 'User'
    
    // If no pending org data, we can still create one from user metadata
    if (pendingError || !pendingOrg) {
      console.log(`No pending org data for user ${user.id}, creating from user metadata`)
    } else {
      username = pendingOrg.username
    }
    
    // Create personal organization
    const orgName = `${username}'s Organization`
    const { data: newOrg, error: orgError } = await supabaseAdmin
      .from('organizations')
      .insert({
        name: orgName
      })
      .select()
      .single()
    
    if (orgError) {
      throw new Error('Failed to create personal organization: ' + orgError.message)
    }
    
    // Add user as admin of their personal organization
    const { error: memberError } = await supabaseAdmin
      .from('organization_members')
      .insert({
        org_id: newOrg.id,
        user_id: user.id,
        role: 'admin'
      })
    
    if (memberError) {
      // Clean up org if member creation fails
      await supabaseAdmin.from('organizations').delete().eq('id', newOrg.id)
      throw new Error('Failed to set up organization membership: ' + memberError.message)
    }
    
    // Mark pending org as processed if it exists
    if (pendingOrg) {
      await supabaseAdmin
        .from('pending_user_orgs')
        .update({ 
          processed: true, 
          processed_at: new Date().toISOString(),
          org_id: newOrg.id 
        })
        .eq('id', pendingOrg.id)
    }
    
    console.log(`Successfully created org ${newOrg.id} for user ${user.id}`)
    
    return new Response(JSON.stringify({ 
      success: true,
      user: {
        id: user.id,
        email: user.email,
        username: user.user_metadata?.username || username
      },
      organization: {
        id: newOrg.id,
        name: newOrg.name
      },
      session: session, // Include session data for frontend authentication
      message: 'Personal organization created successfully!'
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 200,
    })
    
  } catch (error) {
    console.error('Complete user setup error:', error)
    return new Response(JSON.stringify({ 
      error: error.message || 'Failed to complete user setup'
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 400,
    })
  }
}) 
