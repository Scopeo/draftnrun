-- Migration: Add constraints to organization_members
-- 1. Trigger: user can only be in an org once (prevents new duplicates, keeps existing)
-- 2. Trigger: org must always have at least one admin

-- Prevent duplicate memberships (trigger instead of constraint to not break existing data)
CREATE OR REPLACE FUNCTION public.prevent_duplicate_membership()
RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.organization_members
    WHERE user_id = NEW.user_id AND org_id = NEW.org_id
  ) THEN
    RAISE EXCEPTION 'User is already a member of this organization';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER prevent_duplicate_membership_trigger
BEFORE INSERT ON public.organization_members
FOR EACH ROW
EXECUTE FUNCTION public.prevent_duplicate_membership();

-- Create trigger function to enforce minimum one admin per org
CREATE OR REPLACE FUNCTION public.enforce_minimum_admin()
RETURNS TRIGGER AS $$
DECLARE
  admin_count INTEGER;
  org_exists BOOLEAN;
BEGIN
  -- For DELETE: check if we're removing an admin
  IF TG_OP = 'DELETE' AND OLD.role = 'admin' THEN
    -- Allow if org is being deleted (CASCADE)
    SELECT EXISTS(SELECT 1 FROM public.organizations WHERE id = OLD.org_id) INTO org_exists;
    IF NOT org_exists THEN
      RETURN OLD;
    END IF;

    SELECT COUNT(*) INTO admin_count
    FROM public.organization_members
    WHERE org_id = OLD.org_id AND role = 'admin' AND id != OLD.id;

    IF admin_count = 0 THEN
      RAISE EXCEPTION 'Cannot remove the last admin from organization';
    END IF;
  END IF;

  -- For UPDATE: check if we're demoting the last admin
  IF TG_OP = 'UPDATE' AND OLD.role = 'admin' AND NEW.role != 'admin' THEN
    SELECT COUNT(*) INTO admin_count
    FROM public.organization_members
    WHERE org_id = OLD.org_id AND role = 'admin' AND id != OLD.id;

    IF admin_count = 0 THEN
      RAISE EXCEPTION 'Cannot demote the last admin of organization';
    END IF;
  END IF;

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
CREATE TRIGGER enforce_minimum_admin_trigger
BEFORE DELETE OR UPDATE ON public.organization_members
FOR EACH ROW
EXECUTE FUNCTION public.enforce_minimum_admin();
