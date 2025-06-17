import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'
// Assuming you have a shared CORS setup, adjust the path if necessary
import { corsHeaders } from '../_shared/cors.ts'

interface OrganizationMember {
  id: string
  email: string
  role: string
  created_at?: string
}

serve(async (req: Request) => {
  // Handle preflight OPTIONS request for CORS
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const { orgId } = await req.json()
    if (!orgId) {
      return new Response(JSON.stringify({ error: 'Organization ID (orgId) is required.' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 400,
      })
    }

    // Create a Supabase client with the SERVICE_ROLE_KEY for elevated access
    // Ensure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set in your Edge Function's environment variables
    const supabaseAdmin = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
      {
        auth: {
          // It's good practice to explicitly set autoRefreshToken and persistSession to false for admin clients
          autoRefreshToken: false,
          persistSession: false,
        },
      },
    )

    // Create a Supabase client for user context to verify user's org membership
    const authHeader = req.headers.get('Authorization')!
    if (!authHeader) {
        return new Response(JSON.stringify({ error: 'Authorization header is missing.' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 401,
      })
    }
    
    const supabaseUserClient = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_ANON_KEY') ?? '', // Use your public anon key
      { global: { headers: { Authorization: authHeader } } },
    )

    const { data: { user }, error: userError } = await supabaseUserClient.auth.getUser()
    if (userError || !user) {
      console.error('User authentication error:', userError?.message)
      return new Response(JSON.stringify({ error: 'User not authenticated or error fetching user.' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 401,
      })
    }

    // Security Check: Verify the authenticated user is part of the organization
    console.log(`[get-organization-members-details] Performing membership check for user ${user.id} in org ${orgId}`);

    // Use the admin client to check membership
    const { data: memberData, error: memberCheckError, count: memberCount } = await supabaseAdmin
      .from('organization_members')
      .select('user_id', { count: 'exact', head: true }) // head: true is efficient for counts
      .eq('org_id', orgId)
      .eq('user_id', user.id);

    // Log the direct results of the membership check
    console.log(`[get-organization-members-details] Membership check for user ${user.id} in org ${orgId} - Count: ${memberCount}, Error: ${memberCheckError ? memberCheckError.message : 'No error'}`);

    if (memberCheckError) {
      console.error(`[get-organization-members-details] Error during organization membership check: ${memberCheckError.message}`);
      return new Response(JSON.stringify({ error: 'Failed to verify organization membership due to a query error.' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 500,
      });
    }

    // Check if the count is explicitly 0 or null (null might indicate an issue though error should catch it)
    if (memberCount === null || memberCount === 0) {
      console.warn(`[get-organization-members-details] Access Denied: User ${user.id} attempted to access org ${orgId}. Membership count: ${memberCount}.`);
      return new Response(JSON.stringify({ error: 'Access denied: User is not a member of this organization.' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 403, // Forbidden
      });
    }
    
    console.log(`[get-organization-members-details] Membership confirmed for user ${user.id} in org ${orgId}. Proceeding to fetch members.`);

    // Fetch organization members (user_id, role, created_at)
    const { data: memberships, error: membershipError } = await supabaseAdmin
      .from('organization_members')
      .select('user_id, role, created_at')
      .eq('org_id', orgId)

    if (membershipError) {
      console.error('Error fetching memberships:', membershipError.message)
      throw membershipError // Let the generic error handler catch this
    }

    if (!memberships || memberships.length === 0) {
      return new Response(JSON.stringify([]), { // Return empty array if no members
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 200,
      })
    }

    const userIds = memberships.map(m => m.user_id)

    // Fetch user details (emails) from auth.users using the admin client
    // Note: admin.listUsers() can retrieve up to 50 users by default.
    // For orgs with >50 users, pagination would be needed here.
    const { data: usersListResponse, error: usersError } = await supabaseAdmin.auth.admin.listUsers({
      // page: 1, // example for pagination
      // perPage: 50 // example for pagination
    })
    
    if (usersError) {
      console.error('Error fetching users from auth.admin:', usersError.message)
      // Depending on policy, you might return partial data or an error.
      // For now, we'll throw an error.
      throw new Error('Failed to fetch user details for members.')
    }
    
    const relevantUsers = usersListResponse.users.filter(u => userIds.includes(u.id));

    // Combine member details with user emails
    const membersWithDetails: OrganizationMember[] = memberships.map(membership => {
      const authUser = relevantUsers.find(u => u.id === membership.user_id)
      return {
        id: membership.user_id,
        email: authUser?.email || `User ${membership.user_id.substring(0,8)}... (Email not found)`,
        role: membership.role || 'user', // Default role if not set
        created_at: membership.created_at,
      }
    })

    return new Response(JSON.stringify(membersWithDetails), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 200,
    })
  } catch (error) {
    console.error('Error in get-organization-members-details function:', error.message)
    return new Response(JSON.stringify({ error: error.message || 'An unexpected error occurred.' }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 500,
    })
  }
})
