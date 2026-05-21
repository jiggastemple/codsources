import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Expert Sources | Courier Student News',
  description: 'Find College of DuPage faculty experts for your story',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full">{children}</body>
    </html>
  );
}
