import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('http://localhost:3000'),
  title: 'SafeTwin-5G Evidence Dashboard',
  description: 'Fail-closed benchmark and evidence status for the SafeTwin-5G private-network digital twin.',
  openGraph: {
    title: 'SafeTwin-5G — Evidence before autonomy',
    description: 'Fail-closed benchmark and evidence status for a trustworthy autonomous private-network digital twin.',
    images: [{ url: '/og.png', width: 1200, height: 630, alt: 'SafeTwin-5G — Evidence before autonomy' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'SafeTwin-5G — Evidence before autonomy',
    description: 'Fail-closed benchmark and evidence status for a trustworthy autonomous private-network digital twin.',
    images: ['/og.png'],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
