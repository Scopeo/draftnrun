alter table "public"."organization_invitations" add column "has_account" boolean default false;

alter table "public"."organization_invitations" add column "token" uuid;

CREATE UNIQUE INDEX organization_invitations_token_idx ON public.organization_invitations USING btree (token);

set check_function_bodies = off;

CREATE OR REPLACE FUNCTION public.get_user_by_email(email text)
 RETURNS boolean
 LANGUAGE sql
 SECURITY DEFINER
AS $function$
  SELECT EXISTS(SELECT 1 FROM auth.users WHERE auth.users.email = get_user_by_email.email);
$function$
;


