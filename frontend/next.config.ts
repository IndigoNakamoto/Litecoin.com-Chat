import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker deployment
  output: process.env.NODE_ENV === 'production' ? 'standalone' : undefined,
  
  // Base path for litecoin.com/chat integration
  // All routes and assets will be prefixed with /chat
  basePath: '/chat',

  async redirects() {
    return [
      // When this app is hosted at the root of a domain (e.g. chat.lite.space),
      // redirect "/" to the app's basePath entrypoint.
      //
      // `basePath: false` is critical here; otherwise this would only match
      // "/chat/" (because basePath is applied to matchers by default).
      {
        source: '/',
        destination: '/chat',
        permanent: false,
        basePath: false,
      },
    ];
  },
  
  async rewrites() {
    // Server-side rewrite target. In Docker this must be the backend service
    // name; NEXT_PUBLIC_BACKEND_URL is localhost and is for the browser.
    const backendUrl = (
      process.env.BACKEND_INTERNAL_URL?.trim()
      || process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
      || 'http://localhost:8000'
    );
    
    return [
      {
        source: '/api/v1/:path*',
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ]
  },

  async headers() {
    const isProduction = process.env.NODE_ENV === 'production';
    
    // Get API URLs from environment variables (handle empty strings as missing)
    const backendUrl = (process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || 'http://localhost:8000');
    const payloadUrl = (process.env.NEXT_PUBLIC_PAYLOAD_URL?.trim() || 'https://cms.lite.space');
    
    // Extract hostnames from URLs for CSP with error handling
    let backendHost: string;
    let payloadHost: string;
    
    try {
      backendHost = new URL(backendUrl).origin;
    } catch (error) {
      console.warn(`Invalid NEXT_PUBLIC_BACKEND_URL: ${backendUrl}, using default`);
      backendHost = 'http://localhost:8000';
    }
    
    try {
      payloadHost = new URL(payloadUrl).origin;
    } catch (error) {
      console.warn(`Invalid NEXT_PUBLIC_PAYLOAD_URL: ${payloadUrl}, using default`);
      payloadHost = 'https://cms.lite.space';
    }
    
    // Build Content Security Policy
    // Note: Next.js requires 'unsafe-inline' and 'unsafe-eval' for scripts in some cases
    // This can be tightened later with nonces if needed
    // Allow Cloudflare Insights beacon script
    const cspDirectives = [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://static.cloudflareinsights.com",
      "style-src 'self' 'unsafe-inline' fonts.googleapis.com",
      "font-src 'self' fonts.gstatic.com data:",
      "img-src 'self' data: https:",
      `connect-src 'self' ${backendHost} ${payloadHost} https://static.cloudflareinsights.com`,
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join('; ');
    
    const headers = [
      {
        // Apply to all routes
        source: '/:path*',
        headers: [
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'Permissions-Policy',
            value: 'geolocation=(), microphone=(), camera=()',
          },
          {
            key: 'Content-Security-Policy',
            value: cspDirectives,
          },
        ],
      },
    ];
    
    // Only add HSTS in production
    if (isProduction) {
      headers[0].headers.push({
        key: 'Strict-Transport-Security',
        value: 'max-age=31536000; includeSubDomains',
      });
    }
    
    return headers;
  },
}

export default nextConfig;
