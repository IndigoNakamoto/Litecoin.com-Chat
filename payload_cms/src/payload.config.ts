// storage-adapter-import-placeholder
import { mongooseAdapter } from '@payloadcms/db-mongodb'
import { payloadCloudPlugin } from '@payloadcms/payload-cloud'
import { lexicalEditor } from '@payloadcms/richtext-lexical'
import path from 'path'
import { buildConfig } from 'payload'
import { fileURLToPath } from 'url'
import sharp from 'sharp'

import { Users } from './collections/Users'
import { Media } from './collections/Media'
import { Article } from './collections/Article'
import { Category } from './collections/Category'
import { SuggestedQuestions } from './collections/SuggestedQuestions'
import { KnowledgeBase } from './collections/KnowledgeBase'
import Logo from './components/admin/Logo'
import Icon from './components/admin/Icon'

const filename = fileURLToPath(import.meta.url)
const dirname = path.dirname(filename)

// Build CORS and CSRF arrays dynamically based on environment
const frontendUrl = process.env.FRONTEND_URL || (process.env.NODE_ENV === 'production' ? 'https://chat.lite.space' : 'http://localhost:3000')

const corsOrigins = [
  frontendUrl,
  'https://cms.lite.space',
  'https://chat.lite.space',
  'https://litecoin.com',
  'https://www.litecoin.com',
]

const csrfOrigins = [
  frontendUrl,
  'https://cms.lite.space',
  'https://chat.lite.space',
  'https://litecoin.com',
  'https://www.litecoin.com',
]

// Only include localhost URLs in development mode
if (process.env.NODE_ENV !== 'production') {
  corsOrigins.push('http://localhost:3000', 'http://localhost:3001')
  csrfOrigins.push('http://localhost:3000', 'http://localhost:3001')
}

export default buildConfig({
  admin: {
    user: Users.slug,
    autoLogin: false, // Disable auto-login for security
    importMap: {
      baseDir: path.resolve(dirname),
    },
    components: {
      graphics: {
        Logo: Logo as any,
        Icon: Icon as any,
      },
    },
  },
  collections: [Users, Media, Article, Category, SuggestedQuestions, KnowledgeBase],
  cors: corsOrigins,
  csrf: csrfOrigins,
  editor: lexicalEditor({
    features: ({ defaultFeatures }) => [...defaultFeatures],
  }),
  secret: process.env.PAYLOAD_SECRET || '',
  // Use PAYLOAD_PUBLIC_SERVER_URL if explicitly set, otherwise use localhost
  // This ensures the admin panel makes requests to the correct URL when accessing locally
  serverURL: process.env.PAYLOAD_PUBLIC_SERVER_URL || 'http://localhost:3001',
  cookiePrefix: 'payload',
  typescript: {
    outputFile: path.resolve(dirname, 'payload-types.ts'),
  },
  localization: {
    locales: ['en', 'es', 'fr'],
    defaultLocale: 'en',
    fallback: true,
  },
  db: mongooseAdapter({
    url: process.env.DATABASE_URI || '',
  }),
  sharp,
  plugins: [
    payloadCloudPlugin(),
    // storage-adapter-placeholder
  ],
})
