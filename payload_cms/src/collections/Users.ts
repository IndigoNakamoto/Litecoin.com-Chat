import type { CollectionConfig } from 'payload'

export const Users: CollectionConfig = {
  slug: 'users',
  admin: {
    useAsTitle: 'email',
    hidden: ({ user }) => !user || !user.roles?.includes('admin'),
  },
  auth: {
    tokenExpiration: 7200, // 2 hours
    useSessions: true, // Use sessions for better cookie handling
    useAPIKey: true,
  },
  access: {
    create: ({ req }) => {
      const user = req.user
      if (!user) {
        console.log('[Users access] No user found in request')
        return false
      }
      // Ensure roles is an array and check for admin role
      const roles = Array.isArray(user.roles) ? user.roles : []
      const hasAdmin = roles.includes('admin')
      console.log('[Users access] Create check - User:', user.email, 'Roles:', JSON.stringify(roles), 'Has admin:', hasAdmin, 'User object:', JSON.stringify(Object.keys(user)))
      return hasAdmin
    },
    read: ({ req: { user }, id }) => {
      // Ensure roles is an array if user exists
      const roles = user ? (Array.isArray(user.roles) ? user.roles : []) : []

      // If no id provided, this is the current user endpoint (needed for admin panel)
      // Require authentication - fail securely if no user
      if (!id) {
        if (user) {
          console.log('[Users access] Read check - Current user endpoint, User:', user.email, 'Roles:', JSON.stringify(roles))
          return true
        } else {
          // No user and no id - require authentication
          console.log('[Users access] Read check - Current user endpoint, no user found, denying access')
          return false
        }
      }

      // If no user is authenticated but id is provided, deny access
      // This prevents unauthenticated enumeration of user data
      if (!user) {
        console.log('[Users access] Read check - No user authenticated, denying access to user:', id)
        return false
      }

      // If id is provided and matches current user, allow
      if (user.id === id) {
        console.log('[Users access] Read check - User reading own data, User:', user.email)
        return true
      }

      // Allow admins to read all users
      if (roles.includes('admin')) {
        console.log('[Users access] Read check - Admin reading user, User:', user.email, 'Target ID:', id)
        return true
      }

      // Default: deny access (users can only read their own data, or admins can read all)
      console.log('[Users access] Read check - User:', user.email, 'attempted to read user:', id, '- denying access')
      return false
    },
    update: ({ req: { user }, id }) => {
      if (!user) return false
      // Ensure roles is an array and check for admin role
      const roles = Array.isArray(user.roles) ? user.roles : []
      if (roles.includes('admin')) {
        return true
      }
      return user.id === id
    },
    delete: ({ req: { user } }) => {
      if (!user) return false
      // Ensure roles is an array and check for admin role
      const roles = Array.isArray(user.roles) ? user.roles : []
      return roles.includes('admin')
    },
  },
  fields: [
    {
      name: 'roles',
      type: 'select',
      hasMany: true,
      options: ['admin', 'publisher', 'contributor', 'verified-translator'],
      defaultValue: ['contributor'],
      required: true,
      saveToJWT: true,
      access: {
        update: ({ req: { user } }) => {
          if (!user) return false
          // Ensure roles is an array and check for admin role
          const roles = Array.isArray(user.roles) ? user.roles : []
          return roles.includes('admin')
        },
      },
    },
    {
      name: 'authorizedLanguages',
      type: 'select',
      hasMany: true,
      options: ['en', 'es', 'fr'], // Assuming these are your languages
      admin: {
        condition: (data, siblingData) => {
          // Only show for verified-translator role
          const roles = siblingData?.roles || data?.roles || [];
          return Array.isArray(roles) && roles.includes('verified-translator');
        },
      },
    },
    {
      name: 'authorizedCategories',
      type: 'relationship',
      relationTo: 'categories',
      hasMany: true,
      admin: {
        condition: (data, siblingData) => {
          // Only show for contributor role
          const roles = siblingData?.roles || data?.roles || [];
          return Array.isArray(roles) && roles.includes('contributor');
        },
      },
    },
  ],
}
