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
        status: 401
      });
    }
    // Validate JWT & Get User Info
    const token = authHeader.replace("Bearer ", "");
    const { data: user, error: userError } = await supabase.auth.getUser(token);
    if (userError || !user?.user) {
      console.error("Auth Error:", userError);
      return new Response(JSON.stringify({
        error: "Invalid or expired token"
      }), {
        status: 401
      });
    }
    const userId = user.user.id;
    // Parse request body
    const { project_id } = await req.json();
    if (!project_id) {
      return new Response(JSON.stringify({
        error: "Missing project_id in request body"
      }), {
        status: 400
      });
    }
    // Get the organization ID associated with the project
    const { data: project, error: projectError } = await supabase.from("projects").select("org_id").eq("id", project_id).single();
    if (projectError || !project) {
      console.error("Project Query Error:", projectError);
      return new Response(JSON.stringify({
        error: "Project not found"
      }), {
        status: 404
      });
    }
    const org_id = project.org_id;
    // Check if user belongs to the organization
    const { data: membership, error: membershipError } = await supabase.from("organization_members").select("role").eq("org_id", org_id).eq("user_id", userId).single();
    if (membershipError) {
      console.error("Membership Query Error:", membershipError);
    }
    // Determine access
    const hasAccess = Boolean(membership);
    const role = membership ? membership.role : null;
    return new Response(JSON.stringify({
      access: hasAccess,
      role: role
    }), {
      status: hasAccess ? 200 : 403
    });
  } catch (error) {
    console.error("Unexpected Server Error:", error);
    return new Response(JSON.stringify({
      error: "Internal Server Error",
      details: error.message
    }), {
      status: 500
    });
  }
});