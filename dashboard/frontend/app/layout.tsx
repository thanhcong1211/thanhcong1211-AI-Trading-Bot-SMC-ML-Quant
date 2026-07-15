import type { Metadata } from 'next';
import { JetBrains_Mono } from 'next/font/google';
import './globals.css';

const jetBrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '700'],
  variable: '--font-jetbrains-mono'
});

export const metadata: Metadata = {
  title: 'Global Liquidity & Asset Flow Dashboard',
  description: 'Real-time macro liquidity and cross-asset net flow terminal.'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={jetBrainsMono.variable}>
      <body className="min-h-screen bg-terminal-bg font-mono scanline-bg antialiased">{children}</body>
    </html>
  );
}
