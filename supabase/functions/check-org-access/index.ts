import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";
Deno.serve(async (req)=>{
  try {
    // Initialize Supabase Client
    const supabase = createClient(Deno.env.get("SUPABASE_URL"), Deno.env.get("SUPABASE_SERVICE_ROLE_KEY"));
    // Extract JWT from Authorization header
    const authHeader = req.headers.get("Authorization");
    if (!authHeader) {
      return new Response(JSON.stringify({
        error: "Missing Authorization header"
      }), {
        status: 401,
        headers: {
          "Content-Type": "application/json"
        }
      });
    }
    // Validate JWT & Get User Info
    const token = authHeader.replace("Bearer ", "");
    const { data: { user }, error: userError } = await supabase.auth.getUser(token);
    if (userError || !user) {
      console.error("Auth Error:", userError);
      return new Response(JSON.stringify({
        error: "Invalid or expired token"
      }), {
        status: 401,
        headers: {
          "Content-Type": "application/json"
        }
      });
    }
    const userId = user.id;
    // Parse request body
    let org_id = null;
    try {
      const body = await req.json();
      org_id = body.org_id;
    } catch (parseError) {
      return new Response(JSON.stringify({
        error: "Invalid JSON in request body"
      }), {
        status: 400,
        headers: {
          "Content-Type": "application/json"
        }
      });
    }
    if (!org_id) {
      return new Response(JSON.stringify({
        error: "Missing org_id in request body"
      }), {
        status: 400,
        headers: {
          "Content-Type": "application/json"
        }
      });
    }
    // Check if user belongs to the organization
    const { data: memberships, error: membershipError } = await supabase.from("organization_members").select("role").eq("org_id", org_id).eq("user_id", userId).limit(1); // We only need one membership to confirm access and get a role
    if (membershipError) {
      console.error("Supabase Query Error:", membershipError);
      return new Response(JSON.stringify({
        error: "Error checking membership"
      }), {
        status: 500,
        headers: {
          "Content-Type": "application/json"
        }
      });
    }
    // Determine access
    const hasAccess = memberships && memberships.length > 0; // Check if memberships is not null
    if (!hasAccess || !memberships || !memberships[0].role) {
      console.warn(`Access denied or no role found for user ${userId} to organization ${org_id}.`);
      // Return access: false, but still 200 OK if the check was successful but yielded no access
      // Or return 403 if preferred. Let's stick to 200 as the query succeeded.
      return new Response(JSON.stringify({
        access: false,
        role: null
      }), {
        status: 200,
        headers: {
          "Content-Type": "application/json"
        }
      });
    }
    // Get the role from the first membership record
    const role = memberships[0].role;
    console.info(`User ${userId} has access to organization ${org_id} with role: ${role}`);
    return new Response(JSON.stringify({
      access: true,
      role: role
    }), {
      status: 200,
      headers: {
        "Content-Type": "application/json"
      }
    });
  } catch (error) {
    console.error("Unexpected Server Error:", error);
    // Ensure details are only included in non-production
    const errorDetails = error.message;
    // const errorDetails = Deno.env.get("ENVIRONMENT") !== "production" ? error.message : undefined;
    return new Response(JSON.stringify({
      error: "Internal Server Error",
      details: errorDetails
    }), {
      status: 500,
      headers: {
        "Content-Type": "application/json"
      }
    });
  }
});
