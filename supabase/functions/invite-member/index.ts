import { serve } from "https://deno.land/std@0.177.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.7.1"
import { corsHeaders } from "../_shared/cors.ts"
import { sendInvitationEmail } from "../_shared/email.ts"

serve(async (req) => {
  // Handle CORS
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    console.log("Function invoked - parsing request body");
    const body = await req.json();
    console.log("Request body:", JSON.stringify(body));
    
    // Check for required fields
    const { email, orgId, orgName, role, invitedBy } = body;
    
    if (!email || !orgId) {
      console.log("Missing required fields:", { email, orgId });
      throw new Error("Missing required fields: email and orgId are required");
    }
    
    console.log("All required fields present, returning success");
    
    // Create Supabase client
    const supabaseClient = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
    )
    
    // Generate a unique token
    const token = crypto.randomUUID()
    
    // Set expiration date (e.g., 7 days from now)
    const expiresAt = new Date()
    expiresAt.setDate(expiresAt.getDate() + 7)
    
    // Create invitation record
    const { data, error } = await supabaseClient
      .from('organization_invitations')
      .insert({
        email,
        org_id: orgId,
        role,
        invited_by: invitedBy,
        token,
        accepted: false,
        expires_at: expiresAt.toISOString()
      })
      .select()
      .single()
      
    if (error) throw error
    
    // Generate invitation link with token
    const invitationUrl = `${Deno.env.get('PUBLIC_SITE_URL')}/accept-invite?token=${token}`
    
    // Send email
    await sendInvitationEmail({
      email,
      invitationUrl,
      orgName,
      role
    })
    
    return new Response(JSON.stringify({ 
      success: true, 
      message: "Invitation received successfully",
      data: { email, orgId, orgName, role }
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 200,
    });
  } catch (error) {
    console.error("Function error:", error.message);
    return new Response(JSON.stringify({ 
      error: error.message || "Unknown error occurred"
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 400,
    });
  }
})
