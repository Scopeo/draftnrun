// Deno type declarations for Supabase Edge Functions
declare const Deno: {
  env: {
    get(key: string): string | undefined;
  };
};

interface InvitationEmailProps {
  email: string
  invitationUrl: string
  orgName: string
  role: string
}

interface VerificationEmailProps {
  email: string
  verificationUrl: string
  isDevelopment?: boolean
  appUrl?: string
}

export async function sendInvitationEmail({ email, invitationUrl, orgName, role }: InvitationEmailProps) {
  const SENDGRID_API_KEY = Deno.env.get('SENDGRID_API_KEY')
  const FROM_EMAIL = Deno.env.get('FROM_EMAIL')
  const APP_NAME = Deno.env.get('APP_NAME')
  
  if (!SENDGRID_API_KEY) {
    throw new Error('SendGrid API key is missing')
  }

  // Create plain text version
  const textContent = `
You've been invited to join ${orgName}

Hello,

You have been invited to join the organization "${orgName}" as a ${role}.

To accept this invitation, please click on the following link or copy and paste it into your browser:
${invitationUrl}

This invitation link will expire for security reasons. If you have any questions, please contact the organization administrator.

Best regards,
The ${APP_NAME} Team

---
This is an automated message. If you did not expect this invitation, please ignore this email.
To stop receiving emails from ${APP_NAME}, reply with "unsubscribe" in the subject line.
  `.trim()

  // Create HTML version with proper structure
  const htmlContent = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Invitation to join ${orgName}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; padding: 30px; border-radius: 8px; border: 1px solid #e9ecef;">
        <h1 style="color: #212529; margin-bottom: 20px; font-size: 24px;">You've been invited to join ${orgName}</h1>
        
        <p style="margin-bottom: 16px; font-size: 16px;">Hello,</p>
        
        <p style="margin-bottom: 16px; font-size: 16px;">
            You have been invited to join the organization <strong>"${orgName}"</strong> as a <strong>${role}</strong>.
        </p>
        
        <p style="margin-bottom: 20px; font-size: 16px;">
            To accept this invitation, please click on the button below:
        </p>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="${invitationUrl}" 
               style="background-color: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold; font-size: 16px;">
                Accept Invitation
            </a>
        </div>
        
        <p style="margin-bottom: 16px; font-size: 14px; color: #6c757d;">
            If the button doesn't work, you can copy and paste this link into your browser:
        </p>
        <p style="word-break: break-all; font-family: monospace; background-color: #ffffff; padding: 10px; border: 1px solid #dee2e6; border-radius: 4px; font-size: 12px; margin-bottom: 20px;">
            ${invitationUrl}
        </p>
        
        <p style="margin-bottom: 16px; font-size: 14px; color: #6c757d;">
            This invitation link will expire for security reasons. If you have any questions, please contact the organization administrator.
        </p>
        
        <hr style="border: none; border-top: 1px solid #dee2e6; margin: 20px 0;">
        
        <p style="margin-bottom: 8px; font-size: 16px;">
            Best regards,<br>
            The ${APP_NAME} Team
        </p>
        
        <p style="font-size: 12px; color: #6c757d; margin-top: 20px;">
            This is an automated message. If you did not expect this invitation, please ignore this email.
        </p>
    </div>
</body>
</html>
  `.trim()
  
  const response = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${SENDGRID_API_KEY}`,
      'List-Unsubscribe': `<mailto:${FROM_EMAIL}?subject=unsubscribe>`,
    },
    body: JSON.stringify({
      personalizations: [
        {
          to: [{ email }],
          subject: `Invitation to join ${orgName}`,
        },
      ],
      from: { email: FROM_EMAIL, name: APP_NAME },
      reply_to: { email: FROM_EMAIL },
      content: [
        {
          type: 'text/plain',
          value: textContent,
        },
        {
          type: 'text/html',
          value: htmlContent,
        },
      ],
      headers: {
        'List-Unsubscribe': `<mailto:${FROM_EMAIL}?subject=unsubscribe>`,
      },
      tracking_settings: {
        click_tracking: {
          enable: true
        },
        open_tracking: {
          enable: true
        },
        subscription_tracking: {
          enable: true
        }
      },
    }),
  })
  
  if (!response.ok) {
    const errorData = await response.json()
    throw new Error(`Failed to send email: ${JSON.stringify(errorData)}`)
  }
  
  return true
}

export async function sendVerificationEmail({ email, verificationUrl, isDevelopment = false, appUrl }: VerificationEmailProps) {
  const SENDGRID_API_KEY = Deno.env.get('SENDGRID_API_KEY')
  const FROM_EMAIL = Deno.env.get('FROM_EMAIL')
  const APP_NAME = Deno.env.get('APP_NAME')
  
  if (!SENDGRID_API_KEY) {
    throw new Error('SendGrid API key is missing')
  }
  
  // Create environment-specific content
  const envLabel = isDevelopment ? ' [DEVELOPMENT]' : ''
  const subject = `Verify your ${APP_NAME} account${envLabel}`

  // Create plain text version
  const textContent = `
Welcome to ${APP_NAME}!${envLabel}

Thank you for creating an account with ${APP_NAME}. To complete your registration and start using our platform, please verify your email address.

${isDevelopment ? `
DEVELOPMENT ENVIRONMENT
Environment: ${appUrl}

Copy this link to verify your account:
${verificationUrl}

This is a development email - the link above is safe to copy/paste.
` : `
To verify your account, please click on the following link or copy and paste it into your browser:
${verificationUrl}
`}

This verification link will expire in 24 hours for security reasons.

If you didn't create this account, you can safely ignore this email and no account will be created.

Welcome aboard!
The ${APP_NAME} Team

---
This is an automated message. To stop receiving emails from ${APP_NAME}, reply with "unsubscribe" in the subject line.
  `.trim()

  // Create HTML version with proper structure
  let htmlContent = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify your ${APP_NAME} account${envLabel}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; padding: 30px; border-radius: 8px; border: 1px solid #e9ecef;">
        <h1 style="color: #212529; margin-bottom: 20px; font-size: 24px;">Welcome to ${APP_NAME}!${envLabel}</h1>
        
        <p style="margin-bottom: 16px; font-size: 16px;">
            Thank you for creating an account with ${APP_NAME}. To complete your registration and start using our platform, please verify your email address.
        </p>
  `
  
  if (isDevelopment) {
    // For development: Show full URL in plain text for easy copy-paste
    htmlContent += `
        <div style="background-color: #e3f2fd; padding: 20px; border-left: 4px solid #2196f3; margin: 20px 0; border-radius: 4px;">
            <h3 style="color: #1976d2; margin-top: 0; font-size: 18px;">🚀 Development Environment</h3>
            <p style="margin-bottom: 10px; font-size: 14px;"><strong>Environment:</strong> ${appUrl}</p>
            <p style="margin-bottom: 10px; font-size: 14px;"><strong>Copy this link to verify your account:</strong></p>
            <div style="background-color: #ffffff; padding: 12px; border: 1px solid #dee2e6; font-family: monospace; word-break: break-all; font-size: 12px; border-radius: 4px;">
                ${verificationUrl}
            </div>
            <p style="margin-bottom: 0; font-size: 13px; color: #666; margin-top: 10px;"><em>This is a development email - the link above is safe to copy/paste.</em></p>
        </div>
    `
  } else {
    // For production: Normal button
    htmlContent += `
        <div style="text-align: center; margin: 30px 0;">
            <a href="${verificationUrl}" 
               style="background-color: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold; font-size: 16px;">
                Verify Email Address
            </a>
        </div>
    `
  }
  
  htmlContent += `
        <p style="margin-bottom: 16px; font-size: 14px; color: #6c757d;">
            If the ${isDevelopment ? 'link above doesn\'t work' : 'button doesn\'t work'}, you can copy and paste this link into your browser:
        </p>
        <p style="word-break: break-all; font-family: monospace; background-color: #ffffff; padding: 10px; border: 1px solid #dee2e6; border-radius: 4px; font-size: 12px; margin-bottom: 20px;">
            ${verificationUrl}
        </p>
        
        <p style="margin-bottom: 16px; font-size: 14px; color: #6c757d;">
            This verification link will expire in 24 hours for security reasons.
        </p>
        
        <p style="margin-bottom: 20px; font-size: 14px; color: #6c757d;">
            If you didn't create this account, you can safely ignore this email and no account will be created.
        </p>
        
        <hr style="border: none; border-top: 1px solid #dee2e6; margin: 20px 0;">
        
        <p style="margin-bottom: 8px; font-size: 16px;">
            Welcome aboard!<br>
            The ${APP_NAME} Team
        </p>
        
        <p style="font-size: 12px; color: #6c757d; margin-top: 20px;">
            This is an automated message. If you didn't create this account, please ignore this email.
        </p>
    </div>
</body>
</html>
  `.trim()
  
  const response = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${SENDGRID_API_KEY}`,
      'List-Unsubscribe': `<mailto:${FROM_EMAIL}?subject=unsubscribe>`,
    },
    body: JSON.stringify({
      personalizations: [
        {
          to: [{ email }],
          subject: subject,
        },
      ],
      from: { email: FROM_EMAIL, name: APP_NAME },
      reply_to: { email: FROM_EMAIL },
      content: [
        {
          type: 'text/plain',
          value: textContent,
        },
        {
          type: 'text/html',
          value: htmlContent,
        },
      ],
      headers: {
        'List-Unsubscribe': `<mailto:${FROM_EMAIL}?subject=unsubscribe>`,
      },
      tracking_settings: {
        click_tracking: {
          enable: true
        },
        open_tracking: {
          enable: true
        },
        subscription_tracking: {
          enable: true
        }
      },
    }),
  })
  
  if (!response.ok) {
    const errorData = await response.json()
    throw new Error(`Failed to send verification email: ${JSON.stringify(errorData)}`)
  }
  
  return true
}
