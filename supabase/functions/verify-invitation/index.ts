import { serve } from "https://deno.land/std@0.177.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.7.1"
import { corsHeaders } from "../_shared/cors.ts"

serve(async (req) => {
  // Handle CORS
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const { token, userId } = await req.json()
    
    if (!token || !userId) {
      throw new Error('Missing token or userId')
    }
    
    // Create Supabase client
    const supabaseClient = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
    )
    
    // Get the invitation by token
    const { data: invitation, error: invitationError } = await supabaseClient
      .from('organization_invitations')
      .select('*')
      .eq('token', token)
      .eq('accepted', false)
      .single()
    
    if (invitationError || !invitation) {
      throw new Error('Invalid or expired invitation')
    }
    
    // Add user to organization
    const { error: memberError } = await supabaseClient
      .from('organization_members')
      .insert({
        org_id: invitation.org_id,
        user_id: userId,
        role: invitation.role
      })
    
    if (memberError) {
      throw memberError
    }
    
    // Mark invitation as accepted
    const { error: updateError } = await supabaseClient
      .from('organization_invitations')
      .update({ accepted: true })
      .eq('id', invitation.id)
    
    if (updateError) {
      throw updateError
    }
    
    return new Response(JSON.stringify({ 
      success: true,
      data: { 
        orgId: invitation.org_id,
        role: invitation.role
      }
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 200,
    })
  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 400,
    })
  }
})
