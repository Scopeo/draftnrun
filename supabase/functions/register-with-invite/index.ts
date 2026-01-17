import { serve } from "https://deno.land/std@0.177.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.7.1"
import { corsHeaders } from "../_shared/cors.ts"

serve(async (req) => {
  // Handle CORS
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const { email, password, username, inviteToken } = await req.json()
    
    if (!email || !password || !username || !inviteToken) {
      throw new Error('Missing required fields')
    }
    
    // Create Supabase admin client
    const supabaseAdmin = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
    )
    
    // Verify the invitation exists and get details
    const { data: invitation, error: invitationError } = await supabaseAdmin
      .from('organization_invitations')
      .select('*')
      .eq('token', inviteToken)
      .eq('email', email) // Ensure email matches invitation
      .eq('accepted', false)
      .single()
    
    if (invitationError || !invitation) {
      throw new Error('Invalid invitation or email does not match invitation')
    }
    
    // Check if user already exists
    const { data: existingUser, error: userCheckError } = await supabaseAdmin
      .rpc('get_user_by_email', { email })
    
    if (userCheckError) {
      console.warn('Could not check existing user, proceeding with creation:', userCheckError)
    }
    
    if (existingUser) {
      console.log('User with email already exists:', email)
      throw new Error('User with this email already exists')
    }
    
    // Create user with admin client and automatically confirm email
    // Since they clicked the invitation link, we know they have access to the email
    const { data: newUser, error: createError } = await supabaseAdmin.auth.admin.createUser({
      email,
      password,
      email_confirm: true, // This automatically confirms the email
      user_metadata: {
        username,
        full_name: username,
        super_admin: false,
        org_roles: [
          {
            org_id: invitation.org_id,
            role: invitation.role
          }
        ]
      }
    })
    
    if (createError) {
      if (createError.message?.includes('User already registered')) {
        console.log('User already registered (caught during creation):', email)
        throw new Error('User with this email already exists')
      }
      console.error('User creation failed:', createError)
      throw createError
    }
    
    if (!newUser.user) {
      throw new Error('Failed to create user')
    }
    
    console.log('User created successfully via invite:', newUser.user.id, newUser.user.email)
    
    // Add user to organization
    const { error: memberError } = await supabaseAdmin
      .from('organization_members')
      .insert({
        org_id: invitation.org_id,
        user_id: newUser.user.id,
        role: invitation.role
      })
    
    if (memberError) {
      throw memberError
    }
    
    // Mark invitation as accepted
    const { error: updateError } = await supabaseAdmin
      .from('organization_invitations')
      .update({ accepted: true, accepted_at: new Date().toISOString() })
      .eq('id', invitation.id)
    
    if (updateError) {
      throw updateError
    }
    
    // Sign in the user automatically (create session)
    const { data: signInData, error: signInError } = await supabaseAdmin.auth.signInWithPassword({
      email,
      password,
    })
    
    if (signInError) {
      console.warn('Could not create session, but user was created successfully:', signInError)
    }
    
    return new Response(JSON.stringify({ 
      success: true,
      user: {
        id: newUser.user.id,
        email: newUser.user.email,
        username: newUser.user.user_metadata.username,
        email_confirmed: true // Email is automatically confirmed
      },
      session: signInData?.session || null,
      message: 'Account created, email confirmed, and added to organization successfully!'
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 200,
    })
    
  } catch (error) {
    console.error('Registration error:', error)
    return new Response(JSON.stringify({ 
      error: error.message || 'Registration failed'
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 400,
    })
  }
}) 
