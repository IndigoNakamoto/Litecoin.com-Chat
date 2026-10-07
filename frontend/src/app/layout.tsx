import Navigation from '@/components/NavigationMain';
import { AuthProvider } from '@/contexts/AuthContext';
import { ScrollProvider } from '@/contexts/ScrollContext';
import type { Metadata } from 'next';
import { Geist, Geist_Mono, Space_Grotesk, Inter } from 'next/font/google';
import type { ReactNode } from 'react';
import './globals.css';

const metadataBase = new URL('https://litecoin.com');
const chatUrl = 'https://litecoin.com/chat';
const description =
  'Ask anything about Litecoin and get sourced answers on how it works, wallets, payments, and the network.';
const ogImage = {
  url: 'https://litecoin.com/assets/wf-proxy/cdn.prod.website-files.com/621ec1b30feeb6cd8bb9ec25/6760be5bfc596116ef714f74_LTC-site-new2.jpg',
  width: 1200,
  height: 628,
  alt: 'Litecoin',
};

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  variable: '--font-space-grotesk',
  subsets: ['latin'],
  display: 'swap',
});

const inter = Inter({
  variable: '--font-inter',
  subsets: ['latin'],
  display: 'swap',
});

export const metadata: Metadata = {
  metadataBase,
  title: 'Litecoin - Chat',
  description,
  icons: {
    icon: '/favicon.png',
  },
  alternates: {
    canonical: chatUrl,
  },
  openGraph: {
    title: 'Litecoin - Chat',
    description,
    url: chatUrl,
    siteName: 'Litecoin Chat',
    type: 'website',
    images: [ogImage],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Litecoin - Chat',
    description,
    images: [ogImage.url],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${spaceGrotesk.variable} ${inter.variable} antialiased font-sans`}
      >
        <div
          aria-hidden
          className="pointer-events-none fixed inset-0 z-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundColor: '#000', backgroundImage: "url('/chat/bgblack.jpg')" }}
        />
        <div className="relative z-10">
          <AuthProvider>
            <ScrollProvider>
              <Navigation />
              <div className="">{children}</div>
            </ScrollProvider>
          </AuthProvider>
        </div>
      </body>
    </html>
  );
}
