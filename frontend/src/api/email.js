// frontend/src/api/email.js — Email API functions

const API_BASE = 'http://localhost:8000';

/**
 * Verify a lead's email address
 * Auto-verifies if from trusted source (Hunter/FTL/Apollo)
 * SMTP-verifies for other sources
 */
export async function verifyEmail(leadId, email, emailSource) {
  const response = await fetch(`${API_BASE}/leads/${leadId}/verify-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      lead_id: leadId,
      email,
      email_source: emailSource,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Verification failed');
  }

  return response.json();
}

/**
 * Send email to a lead
 * Sends selected variant (A or B)
 * Creates follow-up sequence (J+3, J+7, J+14)
 */
export async function sendEmail(leadId, variant = 'A', sendFollowups = true) {
  const response = await fetch(`${API_BASE}/leads/${leadId}/send-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      variant,
      send_followups: sendFollowups,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Send failed');
  }

  return response.json();
}

/**
 * Update a lead's draft email
 * Allows manual editing before sending
 */
export async function updateDraftEmail(leadId, variant, subject, body, cc) {
  const response = await fetch(`${API_BASE}/leads/${leadId}/draft-email`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      variant,
      subject,
      body,
      cc: cc || null,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Update failed');
  }

  return response.json();
}

/**
 * Batch verify all unverified emails
 * Auto-verifies Hunter/FTL/Apollo
 * SMTP-verifies the rest
 */
export async function batchVerifyEmails() {
  const response = await fetch(`${API_BASE}/leads/batch-verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Batch verify failed');
  }

  return response.json();
}

/**
 * Get lead sequence (all emails in sequence)
 */
export async function getLeadSequence(leadId) {
  const response = await fetch(`${API_BASE}/leads/${leadId}/sequence`);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get sequence');
  }

  return response.json();
}