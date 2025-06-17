interface InvitationEmailProps {
  email: string
  invitationUrl: string
  orgName: string
  role: string
}

export async function sendInvitationEmail({ email, invitationUrl, orgName, role }: InvitationEmailProps) {
  const SENDGRID_API_KEY = Deno.env.get('SENDGRID_API_KEY')
  const FROM_EMAIL = Deno.env.get('FROM_EMAIL')
  const APP_NAME = Deno.env.get('APP_NAME')
  
  if (!SENDGRID_API_KEY) {
    throw new Error('SendGrid API key is missing')
  }
  
  const response = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${SENDGRID_API_KEY}`,
    },
    body: JSON.stringify({
      personalizations: [
        {
          to: [{ email }],
          subject: `Invitation to join ${orgName}`,
        },
      ],
      from: { email: FROM_EMAIL, name: APP_NAME },
      content: [
        {
          type: 'text/html',
          value: `
            <h1>You've been invited to join ${orgName}</h1>
            <p>You've been invited to join ${orgName} as a ${role}.</p>
            <p>Click the link below to accept the invitation:</p>
            <a href="${invitationUrl}">Accept Invitation</a>
          `,
        },
      ],
    }),
  })
  
  if (!response.ok) {
    const errorData = await response.json()
    throw new Error(`Failed to send email: ${JSON.stringify(errorData)}`)
  }
  
  return true
}
