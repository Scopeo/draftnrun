# Invitation System Setup Guide

## Required Environment Variables

Set these environment variables in your Supabase project:

### For Resend Email Integration:
```bash
# Resend API Key
RESEND_API_KEY=

# Email settings
FROM_EMAIL=noreply@yourdomain.com
APP_NAME=Scopeo

# Site URL for invitation links
PUBLIC_SITE_URL=https://yourdomain.com
```

## Deployment Steps

1. **Apply the database migration:**
   ```bash
   supabase db push
   ```

2. **Set environment variables in Supabase:**
   ```bash
   # For local development
   supabase secrets set RESEND_API_KEY=
   supabase secrets set FROM_EMAIL=
   supabase secrets set APP_NAME=
   supabase secrets set PUBLIC_SITE_URL=https://yourdomain.com
   ```

3. **Deploy the Edge Functions:**
   ```bash
   supabase functions deploy invite-member
   supabase functions deploy verify-invitation
   supabase functions deploy register-with-invite
   ```

## What's Included

✅ **invite-member Edge Function** - Checks user existence, creates invitation records, sends emails
✅ **verify-invitation Edge Function** - Handles invitation acceptance and adds users to organizations  
✅ **register-with-invite Edge Function** - Creates accounts for invited users without email confirmation
✅ **accept-invite.vue page** - Frontend for accepting invitations with invitation context
✅ **organization.vue** - Admin interface for sending invitations
✅ **Resend email integration** - Professional HTML email sending
✅ **Database schema** - Tables for invitations and members with proper permissions
✅ **Token preservation** - Invitation tokens are preserved throughout login/register flow
✅ **Invitation context** - Users see who invited them and to which organization
✅ **Enhanced UX** - Clear distinction between login and register flows
✅ **Smart email confirmation** - Skipped for invited users since they clicked email link
✅ **Email validation** - Only invited email can create account (readonly field)

## How It Works

1. Admin invites user via email on organization page
2. `invite-member` function creates invitation record with unique token
3. Email sent via Resend with invitation link containing token
4. User clicks link and lands on `accept-invite` page with invitation context
5. If user needs to authenticate:
   - **For existing users**: Login flow with token preservation
   - **For new users**: Register flow with pre-filled, readonly email
   - Invitation context is shown ("X invited you to join Y as Z")
   - **No email confirmation required** - they already clicked the email link!
6. `register-with-invite` function creates account and adds to organization (for new users)
7. `verify-invitation` function adds existing users to organization

## Testing

Test the complete flow:
1. Go to organization page as admin
2. Enter an email address and click "Invite Member"
3. Check the email sent via Resend
4. Click the invitation link (should stay on accept-invite page)
5. Verify invitation context is shown
6. Test both login and register flows (token should be preserved)
7. Confirm user is added to organization after authentication
8. Test edge cases: refresh page, direct navigation, etc.
