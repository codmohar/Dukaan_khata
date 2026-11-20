"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api, Shop } from "@/lib/api";

const NAV = [
  { href: "/", label: "Dashboard", icon: "🏠" },
  { href: "/voice", label: "Voice Khata", icon: "🎙️" },
  { href: "/scan", label: "Scan Book", icon: "📷" },
  { href: "/customers", label: "Customers", icon: "👥" },
  { href: "/transactions", label: "Ledger", icon: "📒" },
  { href: "/memory", label: "Memory & Rules", icon: "🧠" },
  { href: "/reports", label: "Reports", icon: "📊" },
  { href: "/settings", label: "Settings", icon: "⚙️" },
];

export default function Sidebar() {
  const path = usePathname();
  const [shop, setShop] = useState<Shop | null>(null);
  const [navigatingTo, setNavigatingTo] = useState<string | null>(null);

  useEffect(() => {
    api.shop().then(setShop).catch(() => {});
  }, []);

  useEffect(() => {
    setNavigatingTo(null);
  }, [path]);

  const active = (h: string) => (h === "/" ? path === "/" : path.startsWith(h));

  const startNav = (href: string, label: string) => {
    if (!active(href)) {
      setNavigatingTo(label);
    }
  };

  return (
    <>
      {/* Instant Route Transition Loading Overlay */}
      {navigatingTo && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-white/80 backdrop-blur-sm transition-opacity">
          <div className="fixed top-0 inset-x-0 h-1 bg-emerald-100 overflow-hidden">
            <div className="h-full w-2/3 bg-emerald-600 animate-pulse rounded-r-full" />
          </div>
          <div className="relative flex h-16 w-16 items-center justify-center">
            <div className="absolute inset-0 rounded-full border-4 border-emerald-200" />
            <div className="absolute inset-0 animate-spin rounded-full border-4 border-transparent border-t-emerald-600" />
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600 text-lg font-black text-white shadow-md">
              {shop?.name ? shop.name.charAt(0).toUpperCase() : "D"}
            </div>
          </div>
          <p className="mt-4 text-sm font-bold text-slate-800">
            Opening {navigatingTo}…
          </p>
          <p className="mt-0.5 text-[11px] font-medium text-slate-500">
            Syncing with DukaanAI
          </p>
        </div>
      )}

      {/* Desktop / tablet Sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col bg-slate-950 p-4 text-slate-200 border-r border-slate-800 lg:flex z-30">
        <div className="mb-6 flex items-center gap-3 px-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600 text-xl font-black text-white shadow-lg shadow-emerald-900/50">
            {shop?.name ? shop.name.charAt(0).toUpperCase() : "D"}
          </div>
          <div className="overflow-hidden">
            <div className="text-base font-extrabold tracking-tight text-white truncate">
              {shop?.name || "DukaanAI"}
            </div>
            <p className="text-[11px] font-medium text-emerald-400 truncate">
              {shop?.owner_name ? `Prop: ${shop.owner_name}` : "Voice Digital Khata"}
            </p>
          </div>
        </div>

        <div className="mb-4 px-2">
          <Link
            href="/voice"
            prefetch={true}
            onClick={() => startNav("/voice", "Voice Khata")}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 to-emerald-500 py-3 text-sm font-bold text-white shadow-lg shadow-emerald-900/40 transition hover:from-emerald-500 hover:to-emerald-400 active:scale-95"
          >
            <span>🎙️</span>
            <span>Record Voice</span>
          </Link>
        </div>

        <nav className="flex flex-col gap-1.5 flex-1">
          {NAV.map((n) => {
            const isAct = active(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                prefetch={true}
                onClick={() => startNav(n.href, n.label)}
                className={`flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition ${
                  isAct
                    ? "bg-emerald-600/20 text-emerald-400 border border-emerald-500/30"
                    : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                }`}
              >
                <span className="text-lg">{n.icon}</span>
                <span>{n.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-xs text-slate-400">
          <div className="flex items-center gap-2 mb-1">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-semibold text-slate-300">Voice Assistant Ready</span>
          </div>
          <p className="text-[11px] text-slate-400">
            Say <span className="font-semibold text-emerald-400">&quot;Hi Khata&quot;</span> or tap the speaker/mic sign.
          </p>
        </div>
      </aside>

      {/* Mobile browser bottom navigation bar */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex items-center overflow-x-auto no-scrollbar scroll-smooth border-t border-slate-800 bg-slate-950/95 px-2 py-1.5 backdrop-blur-md lg:hidden pb-[max(0.5rem,env(safe-area-inset-bottom,0px))]">
        <div className="flex w-full items-center justify-between min-w-max sm:min-w-0 sm:justify-around gap-1">
          {NAV.map((n) => {
            const isAct = active(n.href);
            const isVoice = n.href === "/voice";
            return (
              <Link
                key={n.href}
                href={n.href}
                prefetch={true}
                onClick={() => startNav(n.href, n.label)}
                className={`flex flex-col items-center justify-center min-w-[54px] px-2 py-1 text-[11px] font-medium transition active:scale-95 ${
                  isVoice
                    ? isAct
                      ? "text-emerald-400 font-bold"
                      : "text-emerald-500 font-semibold"
                    : isAct
                    ? "text-emerald-400 font-bold"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <span className={`text-xl mb-0.5 ${isVoice ? "scale-110 drop-shadow" : ""}`}>{n.icon}</span>
                <span className="truncate max-w-[64px]">{n.label.split(" ")[0]}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
