import crypto from 'crypto'

/**
 * Deliver a Payload -> backend sync webhook with retry and exponential backoff.
 *
 * The backend reconciles missed documents weekly (`reconcile_embeddings`), so
 * this does not need to be perfect; it only needs to ride out a restarting
 * backend or a brief network blip without losing the publish event.
 *
 * Retries on network errors and 5xx / 429. Does NOT retry on 401 (bad secret)
 * or other 4xx: those will fail identically next time and should be loud.
 */

export type SyncOperation = 'create' | 'update' | 'delete'

const DEFAULT_ATTEMPTS = Number(process.env.SYNC_WEBHOOK_ATTEMPTS || 4)
const BASE_DELAY_MS = Number(process.env.SYNC_WEBHOOK_BASE_DELAY_MS || 1000)
const MAX_DELAY_MS = Number(process.env.SYNC_WEBHOOK_MAX_DELAY_MS || 15000)

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function backoff(attempt: number): number {
  const jitter = Math.floor(Math.random() * 250)
  return Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS) + jitter
}

function isRetryableStatus(status: number): boolean {
  return status === 429 || status >= 500
}

export async function sendSyncWebhook(
  operation: SyncOperation,
  doc: Record<string, unknown>,
  label: string,
): Promise<boolean> {
  const backendUrl = process.env.BACKEND_URL
  if (!backendUrl) {
    console.error('❌ BACKEND_URL environment variable is not set. Cannot trigger RAG pipeline sync.')
    return false
  }

  const payload = JSON.stringify({ operation, doc })
  const webhookSecret = process.env.WEBHOOK_SECRET
  const attempts = Math.max(1, DEFAULT_ATTEMPTS)

  for (let attempt = 0; attempt < attempts; attempt++) {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (webhookSecret) {
      // Fresh timestamp per attempt so replay protection does not reject a retry.
      headers['X-Webhook-Signature'] = crypto.createHmac('sha256', webhookSecret).update(payload).digest('hex')
      headers['X-Webhook-Timestamp'] = Math.floor(Date.now() / 1000).toString()
    } else if (attempt === 0) {
      console.warn('⚠️  WEBHOOK_SECRET not configured - Webhook will be sent without authentication')
    }

    try {
      const response = await fetch(`${backendUrl}/api/v1/sync/payload`, {
        method: 'POST',
        headers,
        body: payload,
      })

      if (response.ok) {
        const result = await response.json().catch(() => ({}))
        console.log(`✅ RAG sync (${operation}) accepted for ${label} on attempt ${attempt + 1}:`, result)
        return true
      }

      const errorText = await response.text().catch(() => '')
      if (response.status === 401) {
        console.error(`🔒 Webhook authentication failed for ${label}. Status 401: ${errorText}`)
        return false
      }
      if (!isRetryableStatus(response.status) || attempt + 1 >= attempts) {
        console.error(
          `❌ RAG sync (${operation}) failed for ${label}. Status ${response.status} after ${attempt + 1} attempt(s): ${errorText}`,
        )
        return false
      }
      const delay = backoff(attempt)
      console.warn(`↻ RAG sync (${operation}) got ${response.status} for ${label}; retrying in ${delay}ms`)
      await sleep(delay)
    } catch (error) {
      if (attempt + 1 >= attempts) {
        console.error(`💥 RAG sync (${operation}) network error for ${label} after ${attempts} attempts:`, error)
        return false
      }
      const delay = backoff(attempt)
      console.warn(`↻ RAG sync (${operation}) network error for ${label}; retrying in ${delay}ms:`, error)
      await sleep(delay)
    }
  }
  return false
}
