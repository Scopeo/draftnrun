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
      console.warn(`[SECURITY] Access denied to manage-super-admins for user ${user.id} - not a super admin`)
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
      console.warn(`[SECURITY] Invalid user attempted access to manage-super-admins: ${user.id}`)
      return new Response(
        JSON.stringify({ error: 'Invalid user session' }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    if (req.method === 'GET') {
      // List all super admins with user details
      const { data: superAdmins, error: saError } = await supabase
        .from('super_admins')
        .select('*')
        .order('created_at', { ascending: false })

      if (saError) {
        throw saError
      }

      // Get user details for each super admin - handle pagination
      let allUsers: any[] = []
      let page = 1
      const perPage = 1000 // Max per page
      
      while (true) {
        const { data: userData, error: userError } = await adminClient.auth.admin.listUsers({
          page,
          perPage
        })
        
        if (userError) {
          throw userError
        }
        
        allUsers = allUsers.concat(userData.users)
        console.log(`[DEBUG] Fetched page ${page}: ${userData.users.length} users (total so far: ${allUsers.length})`)
        
        // If we got fewer users than perPage, we've reached the end
        if (userData.users.length < perPage) {
          break
        }
        
        page++
      }

      // Combine super admin data with user details
      console.log(`[DEBUG] Found ${superAdmins.length} super admins in database`)
      console.log(`[DEBUG] Found ${allUsers.length} total users in auth`)
      
      const superAdminsWithDetails = superAdmins.map(sa => {
        const user = allUsers.find(u => u.id === sa.user_id)
        console.log(`[DEBUG] Mapping super admin ${sa.user_id}: ${user ? `found user ${user.email}` : 'USER NOT FOUND'}`)
        return {
          ...sa,
          email: user?.email || 'Unknown',
          user_metadata: user?.user_metadata
        }
      })
      
      console.log(`[DEBUG] Final super admins with details:`, superAdminsWithDetails.map(sa => ({ id: sa.user_id, email: sa.email })))

      return new Response(
        JSON.stringify({ superAdmins: superAdminsWithDetails }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    if (req.method === 'POST') {
      // Add a new super admin - CRITICAL SECURITY OPERATION
      const { email, notes } = await req.json()
      
      // Log the attempt for security auditing
      console.log(`[SECURITY] Super admin ${user.id} attempting to add new super admin: ${email}`)
      
      if (!email || typeof email !== 'string') {
        console.warn(`[SECURITY] Invalid email provided for super admin addition: ${email}`)
        return new Response(
          JSON.stringify({ error: 'Valid email is required' }),
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // Validate email format
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
      if (!emailRegex.test(email)) {
        console.warn(`[SECURITY] Invalid email format for super admin addition: ${email}`)
        return new Response(
          JSON.stringify({ error: 'Invalid email format' }),
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // Find the user by email - handle pagination
      let allUsers: any[] = []
      let page = 1
      const perPage = 1000
      
      while (true) {
        const { data: userData, error: userError } = await adminClient.auth.admin.listUsers({
          page,
          perPage
        })
        
        if (userError) {
          console.error(`[SECURITY] Error fetching users for super admin addition:`, userError)
          throw userError
        }
        
        allUsers = allUsers.concat(userData.users)
        
        if (userData.users.length < perPage) {
          break
        }
        page++
      }

      const targetUser = allUsers.find(u => u.email === email)
      if (!targetUser) {
        console.warn(`[SECURITY] Attempted to add non-existent user as super admin: ${email}`)
        return new Response(
          JSON.stringify({ error: 'User not found with that email' }),
          { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // Check if user is already a super admin
      const { data: existingCheck } = await supabase
        .from('super_admins')
        .select('id')
        .eq('user_id', targetUser.id)
        .single()

      if (existingCheck) {
        console.warn(`[SECURITY] Attempted to add already existing super admin: ${email}`)
        return new Response(
          JSON.stringify({ error: 'User is already a super admin' }),
          { status: 409, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // Add to super_admins table
      const { error: insertError } = await supabase
        .from('super_admins')
        .insert([{
          user_id: targetUser.id,
          notes: notes || '',
          created_by: user.id
        }])

      if (insertError) {
        console.error(`[SECURITY] Failed to add super admin ${email}:`, insertError)
        throw insertError
      }

      // SUCCESS: Log the security action
      console.log(`[SECURITY] ✅ Super admin successfully added: ${email} (${targetUser.id}) by ${user.id}`)

      return new Response(
        JSON.stringify({ message: 'Super admin added successfully' }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    if (req.method === 'DELETE') {
      // Remove a super admin - CRITICAL SECURITY OPERATION
      const { userId } = await req.json()
      
      // Log the attempt for security auditing
      console.log(`[SECURITY] Super admin ${user.id} attempting to remove super admin: ${userId}`)
      
      if (!userId || typeof userId !== 'string') {
        console.warn(`[SECURITY] Invalid userId provided for super admin removal: ${userId}`)
        return new Response(
          JSON.stringify({ error: 'Valid User ID is required' }),
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // Prevent self-removal (optional safety measure)
      if (userId === user.id) {
        console.warn(`[SECURITY] Super admin ${user.id} attempted to remove themselves`)
        return new Response(
          JSON.stringify({ error: 'Cannot remove yourself as super admin' }),
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // Verify the target user exists in super_admins table
      const { data: existingAdmin, error: checkError } = await supabase
        .from('super_admins')
        .select('id, user_id')
        .eq('user_id', userId)
        .single()

      if (checkError || !existingAdmin) {
        console.warn(`[SECURITY] Attempted to remove non-existent super admin: ${userId}`)
        return new Response(
          JSON.stringify({ error: 'Super admin not found' }),
          { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      const { error: deleteError } = await supabase
        .from('super_admins')
        .delete()
        .eq('user_id', userId)

      if (deleteError) {
        console.error(`[SECURITY] Failed to remove super admin ${userId}:`, deleteError)
        throw deleteError
      }

      // SUCCESS: Log the security action
      console.log(`[SECURITY] ✅ Super admin successfully removed: ${userId} by ${user.id}`)

      return new Response(
        JSON.stringify({ message: 'Super admin removed successfully' }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    return new Response(
      JSON.stringify({ error: 'Method not allowed' }),
      { status: 405, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('Error in manage-super-admins function:', error)
    
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
