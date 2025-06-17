// Define CORS headers
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS'
};
// This test function always says the user doesn't exist
Deno.serve(async (req)=>{
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response('ok', {
      headers: corsHeaders
    });
  }
  try {
    // Get the email and org info from the request body
    const { email, orgId, orgName } = await req.json();
    if (!email) {
      return new Response(JSON.stringify({
        error: 'Missing email parameter'
      }), {
        headers: {
          ...corsHeaders,
          'Content-Type': 'application/json'
        },
        status: 400
      });
    }
    // Always report that the user doesn't exist
    const userExists = false;
    const userId = null;
    // Simulate sending an email
    console.log(`TEST: Sending hello email to ${email} for organization ${orgName}`);
    const message = `Hello email sent to ${email}`;
    // Return the result
    return new Response(JSON.stringify({
      exists: userExists,
      userId: userId,
      message: message
    }), {
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json'
      },
      status: 200
    });
  } catch (error) {
    console.error('Unexpected error:', error);
    return new Response(JSON.stringify({
      error: error.message || 'An unexpected error occurred'
    }), {
      status: 500,
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json'
      }
    });
  }
});
