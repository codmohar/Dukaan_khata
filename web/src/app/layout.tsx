import type { Metadata, Viewport } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import PwaRegistrar from "@/components/PwaRegistrar";
import AuthGate from "@/components/AuthGate";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
  themeColor: "#059669",
};

export const metadata: Metadata = {
  title: "DukaanAI | Voice Digital Khata",
  description: "Multilingual, voice-first digital ledger for Indian kirana shopkeepers",
  manifest: "/manifest.json",
  icons: {
    icon: "/icon.svg",
    apple: "/apple-touch-icon.png",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "DukaanAI",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <PwaRegistrar />
        <AuthGate>
          <Sidebar />
          <main className="mx-auto max-w-6xl p-3 pb-28 lg:ml-60 lg:p-8 lg:pb-8">
            {children}
          </main>
        </AuthGate>
      </body>
    </html>
  );
}
