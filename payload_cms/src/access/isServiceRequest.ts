import crypto from 'crypto'

type HeaderBag = {
  get?: (name: string) => string | null | undefined
} & Record<string, string | undefined>

/**
 * Trusted backend → CMS calls share PAYLOAD_API_KEY as an env secret.
 * That value is not a Payload user API key unless someone enabled one in
 * the admin UI, so `req.user` stays null and collection create would 403.
 * Treat a matching key as a service credential for article writes.
 */
function headerValue(req: { headers?: HeaderBag } | null | undefined, name: string): string | undefined {
  const headers = req?.headers
  if (!headers) return undefined
  if (typeof headers.get === 'function') {
    return headers.get(name) ?? headers.get(name.toLowerCase()) ?? undefined
  }
  return headers[name] ?? headers[name.toLowerCase()]
}

function safeEqual(provided: string, expected: string): boolean {
  const left = Buffer.from(provided)
  const right = Buffer.from(expected)
  if (left.length !== right.length) return false
  return crypto.timingSafeEqual(left, right)
}

export function isServiceRequest(req: { headers?: HeaderBag } | null | undefined): boolean {
  const expected = process.env.PAYLOAD_API_KEY
  if (!expected) {
    console.log('[Service auth] PAYLOAD_API_KEY is not set in the CMS process')
    return false
  }
  if (!req) return false

  const serviceHeader = headerValue(req, 'x-payload-service-key')
  if (serviceHeader && safeEqual(serviceHeader.trim(), expected)) {
    return true
  }

  const authorization = headerValue(req, 'authorization')
  if (!authorization) return false

  const match = authorization.match(/^users\s+API-Key\s+(.+)$/i)
  if (!match) return false
  return safeEqual(match[1].trim(), expected)
}
