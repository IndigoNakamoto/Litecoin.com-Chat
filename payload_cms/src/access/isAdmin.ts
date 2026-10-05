import type { Access } from 'payload'
import { isServiceRequest } from './isServiceRequest'

export const isAdmin: Access = ({ req: { user } }) => {
  // Require authentication - fail securely if no user
  if (!user) {
    return false
  }
  const roles = Array.isArray(user.roles) ? user.roles : []
  return roles.includes('admin')
}

/**
 * Admin or publisher users, plus the backend's trusted service key
 * (`PAYLOAD_API_KEY`, see isServiceRequest). The same credential already
 * creates/updates Articles; allowing it here lets the backend seed and
 * maintain categories and suggested questions. Deletes stay admin-only.
 */
export const isAdminOrPublisher: Access = ({ req }) => {
  if (isServiceRequest(req as any)) {
    return true
  }
  const user = req.user
  // Require authentication - fail securely if no user
  if (!user) {
    return false
  }
  const roles = Array.isArray(user.roles) ? user.roles : []
  return roles.includes('admin') || roles.includes('publisher')
}
