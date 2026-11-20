"use client";
import { useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[];
  readonly userChoice: Promise<{
    outcome: "accepted" | "dismissed";
    platform: string;
  }>;
  prompt(): Promise<void>;
}

export default function PwaRegistrar() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isStandalone, setIsStandalone] = useState(false);
  const [showBanner, setShowBanner] = useState(false);

  useEffect(() => {
    // Register service worker
    if (typeof window !== "undefined" && "serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/sw.js")
        .then(() => console.log("DukaanAI Service Worker registered"))
        .catch((err) => console.log("SW registration failed", err));
    }

    // Check if already running in standalone mode (installed as an app)
    const checkStandalone = () => {
      const isStandaloneMode =
        window.matchMedia("(display-mode: standalone)").matches ||
        (window.navigator as unknown as { standalone?: boolean }).standalone === true ||
        document.referrer.includes("android-app://");
      setIsStandalone(isStandaloneMode);
    };

    checkStandalone();

    // Listen for beforeinstallprompt event
    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
      setShowBanner(true);
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstall);

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstall);
    };
  }, []);

  const handleInstallClick = async () => {
    if (!deferredPrompt) {
      alert("To install DukaanAI as an app:\n\n1. Tap the Chrome menu (⋮) in the top right.\n2. Tap 'Install app' or 'Add to Home screen'.\n\nIt will appear on your phone home screen just like Instagram or Facebook!");
      return;
    }
    await deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === "accepted") {
      setShowBanner(false);
      setDeferredPrompt(null);
    }
  };

  // If already running standalone, no banner needed
  if (isStandalone) return null;

  return (
    <>
      {/* Top Banner on Mobile if opened in Chrome */}
      {showBanner && (
        <div className="fixed top-2 inset-x-2 z-50 flex items-center justify-between gap-3 rounded-2xl bg-gradient-to-r from-emerald-700 to-emerald-900 p-3 text-white shadow-2xl border border-emerald-500/40 lg:hidden animate-in fade-in slide-in-from-top-4">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-emerald-800 font-black shadow">
              D
            </div>
            <div className="min-w-0">
              <p className="text-xs font-bold leading-tight truncate">Install DukaanAI App</p>
              <p className="text-[10px] text-emerald-200">Opens standalone, no Chrome address bar</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={handleInstallClick}
              className="rounded-xl bg-white px-3 py-1.5 text-xs font-extrabold text-emerald-800 shadow hover:bg-emerald-50 active:scale-95"
            >
              Install
            </button>
            <button
              onClick={() => setShowBanner(false)}
              className="p-1 text-emerald-300 hover:text-white text-xs"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </>
  );
}

