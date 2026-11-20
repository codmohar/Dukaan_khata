"use client";
import { useEffect, useState } from "react";
import { API, api, Shop } from "@/lib/api";
import { LANGS, PageTitle } from "@/components/ui";
import { useRealtimeStatus } from "@/lib/supabase";

export default function SettingsPage() {
  const [shopName, setShopName] = useState("Sri Lakshmi Kirana Store");
  const [ownerName, setOwnerName] = useState("Manjunath Gowda");
  const [phone, setPhone] = useState("+91 98450 00000");
  const [language, setLanguage] = useState("kn-IN");
  const [saved, setSaved] = useState(false);
  const [serverStatus, setServerStatus] = useState<"checking" | "online" | "offline">("checking");
  const [backendMeta, setBackendMeta] = useState<{ default_shop_id?: string; speech_provider?: string; model?: string }>({});

  const isRealtime = useRealtimeStatus();

  useEffect(() => {
    // Load local storage preferences
    const localLang = localStorage.getItem("dukaan_lang") || "kn-IN";
    setLanguage(localLang);

    // Fetch backend shop info and health
    api.shop()
      .then((s) => {
        setShopName(s.name);
        if (s.owner_name) setOwnerName(s.owner_name);
        if (s.phone) setPhone(s.phone);
        if (s.language) setLanguage(s.language);
      })
      .catch(() => {
        // Fallback to localStorage if backend shop route not available
        const localShop = localStorage.getItem("dukaan_shop");
        if (localShop) setShopName(localShop);
      });

    api.health()
      .then((h) => {
        setServerStatus("online");
        setBackendMeta(h);
      })
      .catch(() => setServerStatus("offline"));
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    localStorage.setItem("dukaan_shop", shopName);
    localStorage.setItem("dukaan_lang", language);

    try {
      await api.updateShop({
        name: shopName,
        owner_name: ownerName,
        phone,
        language,
      });
    } catch {
      // ignore if shop update route fails
    }

    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <>
      <PageTitle title="Dukaan Settings" sub="Shop profile, regional voice settings, and system connectivity" />

      <div className="grid gap-6 md:grid-cols-2">
        {/* Shop Profile Form */}
        <form onSubmit={handleSave} className="card space-y-4 shadow-sm border border-slate-200">
          <h2 className="font-bold text-slate-900 border-b border-slate-100 pb-2 text-base">
            Shop Information
          </h2>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
              Kirana Shop Name *
            </label>
            <input
              className="input font-semibold"
              value={shopName}
              onChange={(e) => setShopName(e.target.value)}
              placeholder="Sri Lakshmi Stores"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
              Shopkeeper / Owner Name
            </label>
            <input
              className="input"
              value={ownerName}
              onChange={(e) => setOwnerName(e.target.value)}
              placeholder="Manjunath Gowda"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
              Shop Phone Number (for WhatsApp remittances)
            </label>
            <input
              className="input"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+91 98450 00000"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5">
              Default Voice Khata Language
            </label>
            <div className="grid grid-cols-3 gap-2">
              {LANGS.map((l) => (
                <button
                  type="button"
                  key={l.code}
                  onClick={() => setLanguage(l.code)}
                  className={`btn py-2 text-xs font-bold ${
                    language === l.code
                      ? "bg-emerald-600 text-white shadow-sm"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  {l.label.split(" ")[0]}
                </button>
              ))}
            </div>
          </div>

          <button
            type="submit"
            className="btn w-full bg-emerald-600 text-white hover:bg-emerald-700 font-bold py-2.5 shadow-sm"
          >
            {saved ? "✓ Changes Saved!" : "Save Shop Settings"}
          </button>
        </form>

        {/* Connectivity & Diagnostic Box */}
        <div className="space-y-4">
          <div className="card shadow-sm border border-slate-200">
            <h2 className="font-bold text-slate-900 border-b border-slate-100 pb-2 text-base">
              System & Real-Time Sync Status
            </h2>

            <div className="space-y-3 mt-3 text-sm">
              <div className="flex items-center justify-between py-1.5 border-b border-slate-50">
                <span className="text-slate-600">FastAPI Backend:</span>
                <span className="font-mono text-xs flex items-center gap-1.5 font-bold">
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${
                      serverStatus === "online" ? "bg-emerald-500" : "bg-red-500"
                    }`}
                  />
                  {serverStatus === "online" ? "🟢 Connected (Port 8000)" : "🔴 Offline / Unreachable"}
                </span>
              </div>

              <div className="flex items-center justify-between py-1.5 border-b border-slate-50">
                <span className="text-slate-600">Database & Realtime:</span>
                <span className="font-mono text-xs flex items-center gap-1.5 font-bold">
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${
                      isRealtime ? "bg-emerald-500 animate-pulse" : "bg-amber-400"
                    }`}
                  />
                  {isRealtime ? "🟢 Supabase Realtime Active" : "🟡 Polling Sync (5s)"}
                </span>
              </div>

              <div className="flex items-center justify-between py-1.5 border-b border-slate-50">
                <span className="text-slate-600">Voice AI Orchestrator:</span>
                <span className="font-mono text-xs text-slate-700">
                  {backendMeta.model || "Gemini 2.5 Flash"}
                </span>
              </div>

              <div className="flex items-center justify-between py-1.5">
                <span className="text-slate-600">Speech Provider:</span>
                <span className="font-mono text-xs uppercase text-slate-700">
                  {backendMeta.speech_provider || "Gnani Prisma / Sarvam"}
                </span>
              </div>
            </div>
          </div>

          <div className="card shadow-sm border border-slate-200 bg-slate-900 text-slate-200">
            <h3 className="font-bold text-white text-sm mb-1 flex items-center gap-2">
              <span>📱</span> Mobile & Wake-Word Architecture
            </h3>
            <p className="text-xs text-slate-300 leading-relaxed">
              The companion React Native Expo mobile app is equipped with offline Porcupine keyword detection
              for <span className="text-emerald-400 font-bold">&quot;Hey Dukaan&quot;</span> and an Android
              foreground service, ensuring voice khata is ready even when the phone screen is locked.
            </p>
            <div className="mt-3 rounded-lg bg-slate-800/80 p-2.5 font-mono text-[11px] text-slate-300">
              API Base: {API}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
