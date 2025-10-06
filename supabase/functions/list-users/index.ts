import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'
import { corsHeaders } from '../_shared/cors.ts'

Deno.serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    // Get the authorization header
    const authHeader = req.headers.get('Authorization')
    if (!authHeader) {
      return new Response(
        JSON.stringify({ error: 'Missing authorization header' }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // Create Supabase client for user verification
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!
    const supabaseKey = Deno.env.get('SUPABASE_ANON_KEY')!
    const supabase = createClient(supabaseUrl, supabaseKey, {
      global: { headers: { Authorization: authHeader } }
    })

    // Verify the user is authenticated
    const { data: { user }, error: userError } = await supabase.auth.getUser()
    if (userError || !user) {
      return new Response(
        JSON.stringify({ error: 'Unauthorized' }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // SECURITY: Double-check super admin status using database function
    const { data: isSuperAdminData, error: superAdminError } = await supabase
      .rpc('is_super_admin', { user_id: user.id })

    // Log security check for auditing (only log user ID, not sensitive data)
    console.log(`[SECURITY] Super admin check for user ${user.id}: ${isSuperAdminData ? 'GRANTED' : 'DENIED'}`)

    if (superAdminError) {
      console.error(`[SECURITY] Super admin check error for user ${user.id}:`, superAdminError)
      return new Response(
        JSON.stringify({ error: 'Security verification failed' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    if (!isSuperAdminData) {
      console.warn(`[SECURITY] Access denied to list-users for user ${user.id} - not a super admin`)
      return new Response(
        JSON.stringify({ error: 'Access denied - Super admin privileges required' }),
        { status: 403, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // Create admin client with service role
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    const adminClient = createClient(supabaseUrl, supabaseServiceKey)

    // Additional security: Verify user still exists and is active
    const { data: userCheck, error: userCheckError } = await adminClient.auth.admin.getUserById(user.id)
    if (userCheckError || !userCheck.user) {
      console.warn(`[SECURITY] Invalid user attempted access to list-users: ${user.id}`)
      return new Response(
        JSON.stringify({ error: 'Invalid user session' }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    if (req.method === 'GET') {
      // List all users - SENSITIVE OPERATION
      console.log(`[SECURITY] Super admin ${user.id} listing all users`)
      
      // Handle pagination to get ALL users
      let allUsers: any[] = []
      let page = 1
      const perPage = 1000
      
      while (true) {
        const { data, error } = await adminClient.auth.admin.listUsers({
          page,
          perPage
        })
        
        if (error) {
          console.error(`[SECURITY] Error listing users for super admin ${user.id}:`, error)
          throw error
        }
        
        allUsers = allUsers.concat(data.users)
        console.log(`[DEBUG] Fetched page ${page}: ${data.users.length} users (total so far: ${allUsers.length})`)
        
        if (data.users.length < perPage) {
          break
        }
        page++
      }

      // Return user data (excluding sensitive information)
      const users = allUsers.map(user => ({
        id: user.id,
        email: user.email,
        created_at: user.created_at,
        last_sign_in_at: user.last_sign_in_at,
        email_confirmed_at: user.email_confirmed_at,
        user_metadata: user.user_metadata
      }))

      console.log(`[SECURITY] ✅ Successfully listed ${users.length} users for super admin ${user.id}`)

      return new Response(
        JSON.stringify({ users }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    if (req.method === 'POST') {
      // Find user by email - SENSITIVE OPERATION
      const { email } = await req.json()
      
      console.log(`[SECURITY] Super admin ${user.id} searching for user by email: ${email}`)
      
      if (!email || typeof email !== 'string') {
        console.warn(`[SECURITY] Invalid email provided for user search: ${email}`)
        return new Response(
          JSON.stringify({ error: 'Valid email is required' }),
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // Validate email format
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
      if (!emailRegex.test(email)) {
        console.warn(`[SECURITY] Invalid email format for user search: ${email}`)
        return new Response(
          JSON.stringify({ error: 'Invalid email format' }),
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // Handle pagination to search ALL users
      let allUsers: any[] = []
      let page = 1
      const perPage = 1000
      
      while (true) {
        const { data, error } = await adminClient.auth.admin.listUsers({
          page,
          perPage
        })
        
        if (error) {
          console.error(`[SECURITY] Error searching users for super admin ${user.id}:`, error)
          throw error
        }
        
        allUsers = allUsers.concat(data.users)
        
        if (data.users.length < perPage) {
          break
        }
        page++
      }

      const foundUser = allUsers.find(u => u.email === email)
      
      if (!foundUser) {
        console.warn(`[SECURITY] User not found by email search from super admin ${user.id}: ${email}`)
        return new Response(
          JSON.stringify({ error: 'User not found with that email' }),
          { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      console.log(`[SECURITY] ✅ Successfully found user by email for super admin ${user.id}: ${email} → ${foundUser.id}`)

      return new Response(
        JSON.stringify({ 
          user: {
            id: foundUser.id,
            email: foundUser.email,
            created_at: foundUser.created_at,
            user_metadata: foundUser.user_metadata
          }
        }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    return new Response(
      JSON.stringify({ error: 'Method not allowed' }),
      { status: 405, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('Error in list-users function:', error)
    
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
