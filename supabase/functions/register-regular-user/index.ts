import { serve } from "https://deno.land/std@0.177.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.7.1"
import { corsHeaders } from "../_shared/cors.ts"
import { sendVerificationEmail } from "../_shared/email.ts"

serve(async (req) => {
  console.log('🚀 Function invoked - register-regular-user')
  console.log('Request method:', req.method)
  console.log('Request headers:', Object.fromEntries(req.headers.entries()))
  
  if (req.method === 'OPTIONS') {
    console.log('Handling OPTIONS request')
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    console.log('Parsing request body...')
    let requestBody
    try {
      requestBody = await req.json()
      console.log('Raw request body:', requestBody)
    } catch (jsonError) {
      console.error('Failed to parse JSON:', jsonError)
      throw new Error('Invalid JSON in request body')
    }
    
    const { email, password, username, appUrl } = requestBody
    console.log('Request body parsed successfully:', { 
      email, 
      username, 
      appUrl: appUrl ? 'present' : 'missing',
      hasPassword: !!password
    })
    
    if (!email || !password || !username || !appUrl) {
      console.error('Missing required fields:', { email: !!email, password: !!password, username: !!username, appUrl: !!appUrl })
      throw new Error('Missing required fields: email, password, username, appUrl')
    }
    
    const supabaseAdmin = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
    )
    
    // Determine if this is a development environment
    const productionUrl = Deno.env.get('PUBLIC_SITE_URL') || 'https://app.draftnrun.com'
    const isStaging = appUrl.includes('staging--ai-tailor.netlify.app')
    const isLocalDev = appUrl.includes('localhost')
    const isDevelopment = isStaging || isLocalDev
    
    console.log('Environment detection:', {
      appUrl,
      productionUrl,
      isStaging,
      isLocalDev,
      isDevelopment
    })
    
    // Check if user already exists and get their details
    const { data: existingUser, error: userCheckError } = await supabaseAdmin
      .rpc('get_user_by_email', { email })
    
    if (userCheckError) {
      console.warn('Could not check existing user, proceeding with creation:', userCheckError)
    }
    
    if (existingUser) {
      console.log('User with email already exists, checking verification status:', email)
      
      // Get the full user details to check email verification status
      const { data: usersList } = await supabaseAdmin.auth.admin.listUsers()
      const fullUserData = usersList.users.find(user => user.email === email)
      
      if (fullUserData) {
        if (fullUserData.email_confirmed_at) {
          // User exists and is already verified
          console.log('User already exists and is verified:', email)
          return new Response(JSON.stringify({ 
            success: false,
            alreadyExists: true,
            emailVerified: true,
            message: 'An account with this email already exists and is verified. Please sign in instead.'
          }), {
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
            status: 409, // Conflict
          })
        } else {
          // User exists but email is not verified - resend verification
          console.log('User exists but email not verified, resending verification:', email)
          
          // Generate new verification link
          const redirectUrl = `${appUrl}/verify-email?type=signup`
          console.log('Generating new verification link with redirectTo:', redirectUrl)
          
          const { data: linkData, error: linkError } = await supabaseAdmin.auth.admin.generateLink({
            type: 'signup',
            email: email,
            options: {
              redirectTo: redirectUrl
            }
          })
          
          if (linkError || !linkData.properties?.action_link) {
            console.error('Failed to generate verification link:', linkError)
            throw new Error('Failed to generate verification link')
          }
          
          // Extract token and create custom verification URL
          const originalUrl = new URL(linkData.properties.action_link)
          const token = originalUrl.searchParams.get('token')
          
          if (!token) {
            throw new Error('Could not extract verification token')
          }
          
          const supabaseUrl = Deno.env.get('SUPABASE_URL')
          const verificationUrl = `${supabaseUrl}/auth/v1/verify?token=${token}&type=signup&redirect_to=${encodeURIComponent(redirectUrl)}`
          
          console.log(`🔧 Created new verification URL for existing user:`, verificationUrl)
          
          // Send verification email
          await sendVerificationEmail({
            email,
            verificationUrl,
            isDevelopment,
            appUrl
          })
          
          console.log(`Verification email resent to existing user: ${email}`)
          
          return new Response(JSON.stringify({ 
            success: true,
            alreadyExists: true,
            emailVerified: false,
            user: {
              id: fullUserData.id,
              email: fullUserData.email,
              username: fullUserData.user_metadata?.username || username,
              email_confirmed: false
            },
            message: 'Account exists but email not verified. A new verification email has been sent to your email address.'
          }), {
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
            status: 200,
          })
        }
      } else {
        console.error('User exists according to RPC but not found in user list')
        throw new Error('User verification status could not be determined')
      }
    }
    
    // Create user with email confirmation disabled initially
    const { data: newUser, error: createError } = await supabaseAdmin.auth.admin.createUser({
      email,
      password,
      email_confirm: false, // We'll handle verification via email
      user_metadata: {
        username,
        full_name: username,
        super_admin: false
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
      throw new Error('Failed to create user account')
    }
    
    console.log('User created successfully:', newUser.user.id, newUser.user.email)
    
    // Generate verification link using Supabase's built-in system
    const redirectUrl = `${appUrl}/verify-email?type=signup`
    console.log('Generating verification link with redirectTo:', redirectUrl)
    
    const { data: linkData, error: linkError } = await supabaseAdmin.auth.admin.generateLink({
      type: 'signup',
      email: email,
      options: {
        redirectTo: redirectUrl
      }
    })
    
    if (linkError || !linkData.properties?.action_link) {
      console.error('Failed to generate verification link:', linkError)
      throw new Error('Failed to generate verification link')
    }
    
    let verificationUrl
    
    // Always create custom verification URLs to avoid Site URL conflicts
    // Extract just the token from Supabase's generated link
    const originalUrl = new URL(linkData.properties.action_link)
    const token = originalUrl.searchParams.get('token')
    
    if (!token) {
      throw new Error('Could not extract verification token')
    }
    
    // Manually construct the verification URL with the correct redirect based on appUrl
    const supabaseUrl = Deno.env.get('SUPABASE_URL')
    verificationUrl = `${supabaseUrl}/auth/v1/verify?token=${token}&type=signup&redirect_to=${encodeURIComponent(redirectUrl)}`
    
    console.log(`🔧 Created custom verification URL for ${isDevelopment ? 'development' : 'production'}:`, verificationUrl)
    
    // Send verification email with environment-specific content
    await sendVerificationEmail({
      email,
      verificationUrl,
      isDevelopment,
      appUrl
    })
    
    // Store user info for org creation after email verification
    const { error: pendingOrgError } = await supabaseAdmin
      .from('pending_user_orgs')
      .insert({
        user_id: newUser.user.id,
        username: username,
        email: email
      })
    
    if (pendingOrgError) {
      console.error('Failed to store pending org data:', pendingOrgError.message)
    }
    
    console.log(`User ${newUser.user.id} created, verification email sent to ${email} (${isDevelopment ? 'DEV' : 'PROD'})`)
    
    return new Response(JSON.stringify({ 
      success: true,
      user: {
        id: newUser.user.id,
        email: newUser.user.email,
        username: newUser.user.user_metadata?.username || username,
        email_confirmed: false
      },
      message: 'Account created successfully! Please check your email to verify your account.'
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
