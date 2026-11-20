"use client";
import React, { createContext, useContext, useEffect, useState } from "react";
import { api, getCurrentShopId, setCurrentShopId, Shop } from "@/lib/api";
import { LANGS } from "@/components/ui";

interface AuthContextType {
  shop: Shop | null;
  loading: boolean;
  login: (shopId?: string, phone?: string, pin?: string) => Promise<void>;
  register: (data: { name: string; owner_name: string; phone: string; language: string; pin: string }) => Promise<void>;
  logout: () => void;
  availableShops: Shop[];
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthGate");
  return ctx;
}

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [shop, setShop] = useState<Shop | null>(null);
  const [loading, setLoading] = useState(true);
  const [availableShops, setAvailableShops] = useState<Shop[]>([]);

  // Auth screen state
  const [tab, setTab] = useState<"quick" | "phone" | "new">("quick");
  const [phone, setPhone] = useState("");
  const [pin, setPin] = useState("1234");
  const [selectedShopId, setSelectedShopId] = useState<string>("");

  // New shop registration state
  const [newName, setNewName] = useState("");
  const [newOwner, setNewOwner] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newLang, setNewLang] = useState("kn-IN");
  const [newPin, setNewPin] = useState("1234");

  const [submitting, setSubmitting] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authSuccess, setAuthSuccess] = useState("");

  const refreshShops = async () => {
    try {
      const list = await api.getShops();
      setAvailableShops(list);
      if (list.length > 0 && !selectedShopId) {
        setSelectedShopId(list[0].id);
      }
    } catch {
      // Backend may be starting
    }
  };

  useEffect(() => {
    const savedId = getCurrentShopId();
    refreshShops();

    if (savedId) {
      // User has existing session: verify & load
      api
        .authMe()
        .then((s) => {
          setShop(s);
          setLoading(false);
        })
        .catch(() => {
          // If saved shop doesn't exist anymore, clear and show login
          setCurrentShopId("");
          setShop(null);
          setLoading(false);
        });
    } else {
      setLoading(false);
    }
  }, []);

  const handleLogin = async (shopId?: string, ph?: string, p?: string) => {
    setAuthError("");
    setSubmitting(true);
    try {
      const res = await api.login({
        shop_id: shopId || undefined,
        phone: ph || undefined,
        pin: p || undefined,
      });
      setShop(res.shop);
      setAuthSuccess(res.message);
      await refreshShops();
    } catch (err: any) {
      setAuthError(err.message || "Failed to log in to Dukaan.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRegister = async (data: {
    name: string;
    owner_name: string;
    phone: string;
    language: string;
    pin: string;
  }) => {
    setAuthError("");
    setSubmitting(true);
    try {
      const res = await api.registerShop(data);
      setShop(res.shop);
      setAuthSuccess(res.message);
      await refreshShops();
    } catch (err: any) {
      setAuthError(err.message || "Failed to create virtual dukaan.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleLogout = () => {
    api.logout();
    setShop(null);
    setAuthSuccess("");
    setAuthError("");
    refreshShops();
  };

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 text-white">
        <div className="relative flex h-16 w-16 items-center justify-center">
          <div className="absolute inset-0 animate-spin rounded-full border-4 border-emerald-500 border-t-transparent" />
          <span className="text-2xl">🏪</span>
        </div>
        <p className="mt-4 text-sm font-bold text-slate-300">Opening DukaanAI Khata…</p>
      </div>
    );
  }

  // If already authenticated, show the personal dukaan!
  if (shop) {
    return (
      <AuthContext.Provider
        value={{
          shop,
          loading,
          login: handleLogin,
          register: handleRegister,
          logout: handleLogout,
          availableShops,
        }}
      >
        {children}
      </AuthContext.Provider>
    );
  }

  // Otherwise, render Kirana Dukaandar Authentication Screen
  return (
    <div className="min-h-screen bg-slate-950 px-4 py-8 flex flex-col items-center justify-center">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-tr from-emerald-600 to-emerald-400 text-3xl shadow-lg shadow-emerald-900/50 mb-3">
            🏪
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white sm:text-3xl">
            DukaanAI Khata
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Voice-First Digital Ledger for Indian Kirana Shopkeepers
          </p>
        </div>

        {/* Auth Box */}
        <div className="rounded-3xl border border-slate-800 bg-slate-900/90 p-5 shadow-2xl backdrop-blur-md">
          {/* Tabs */}
          <div className="grid grid-cols-3 gap-1 rounded-2xl bg-slate-950 p-1 mb-5">
            <button
              onClick={() => {
                setTab("quick");
                setAuthError("");
              }}
              className={`rounded-xl py-2 text-xs font-bold transition ${
                tab === "quick"
                  ? "bg-emerald-600 text-white shadow-md"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              🏪 My Dukaan
            </button>
            <button
              onClick={() => {
                setTab("phone");
                setAuthError("");
              }}
              className={`rounded-xl py-2 text-xs font-bold transition ${
                tab === "phone"
                  ? "bg-emerald-600 text-white shadow-md"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              📱 Mobile
            </button>
            <button
              onClick={() => {
                setTab("new");
                setAuthError("");
              }}
              className={`rounded-xl py-2 text-xs font-bold transition ${
                tab === "new"
                  ? "bg-emerald-600 text-white shadow-md"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              ✨ New Shop
            </button>
          </div>

          {authError && (
            <div className="mb-4 rounded-xl border border-red-500/40 bg-red-950/60 p-3 text-xs font-medium text-red-200">
              ⚠️ {authError}
            </div>
          )}

          {authSuccess && (
            <div className="mb-4 rounded-xl border border-emerald-500/40 bg-emerald-950/60 p-3 text-xs font-medium text-emerald-200">
              {authSuccess}
            </div>
          )}

          {/* TAB 1: QUICK 1-TAP DUKAAN SELECT */}
          {tab === "quick" && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-300 mb-1.5">
                  Select Your Virtual Dukaan:
                </label>
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {availableShops.map((s) => {
                    const isSelected = selectedShopId === s.id;
                    return (
                      <div
                        key={s.id}
                        onClick={() => setSelectedShopId(s.id)}
                        className={`cursor-pointer rounded-2xl border p-3 transition flex items-center justify-between ${
                          isSelected
                            ? "border-emerald-500 bg-emerald-950/40 shadow-md ring-1 ring-emerald-500/40"
                            : "border-slate-800 bg-slate-950/60 hover:border-slate-700"
                        }`}
                      >
                        <div className="overflow-hidden">
                          <p className="font-bold text-sm text-white truncate">{s.name}</p>
                          <p className="text-[11px] text-slate-400 truncate">
                            {s.owner_name ? `Prop: ${s.owner_name}` : "Kirana Store"} • {s.phone || "No phone"}
                          </p>
                        </div>
                        <div
                          className={`flex h-5 w-5 items-center justify-center rounded-full border text-[10px] ${
                            isSelected
                              ? "border-emerald-500 bg-emerald-500 text-white font-black"
                              : "border-slate-700"
                          }`}
                        >
                          {isSelected ? "✓" : ""}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-300 mb-1">
                  Security PIN:
                </label>
                <input
                  type="password"
                  maxLength={6}
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  placeholder="Enter 4-digit PIN (default 1234)"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <button
                disabled={submitting || !selectedShopId}
                onClick={() => handleLogin(selectedShopId, undefined, pin)}
                className="w-full rounded-xl bg-gradient-to-r from-emerald-600 to-emerald-500 py-3.5 text-sm font-bold text-white shadow-lg shadow-emerald-900/40 transition hover:from-emerald-500 hover:to-emerald-400 disabled:opacity-50 active:scale-95"
              >
                {submitting ? "Opening Dukaan…" : "🔓 Open My Virtual Dukaan"}
              </button>
            </div>
          )}

          {/* TAB 2: PHONE & PIN LOGIN */}
          {tab === "phone" && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-300 mb-1">
                  Registered Mobile Number:
                </label>
                <div className="flex rounded-xl border border-slate-700 bg-slate-950 overflow-hidden focus-within:border-emerald-500">
                  <span className="flex items-center px-3 text-xs font-bold text-slate-400 bg-slate-900 border-r border-slate-800">
                    +91
                  </span>
                  <input
                    type="tel"
                    maxLength={10}
                    value={phone}
                    onChange={(e) => setPhone(e.target.value.replace(/[^0-9]/g, ""))}
                    placeholder="e.g. 9845000000"
                    className="w-full bg-transparent px-3 py-2.5 text-sm text-white outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-300 mb-1">
                  4-Digit Security PIN:
                </label>
                <input
                  type="password"
                  maxLength={6}
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  placeholder="Enter PIN (e.g. 1234)"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <button
                disabled={submitting || phone.length < 10}
                onClick={() => handleLogin(undefined, phone, pin)}
                className="w-full rounded-xl bg-gradient-to-r from-emerald-600 to-emerald-500 py-3.5 text-sm font-bold text-white shadow-lg shadow-emerald-900/40 transition hover:from-emerald-500 hover:to-emerald-400 disabled:opacity-50 active:scale-95"
              >
                {submitting ? "Verifying…" : "🚀 Login with Mobile"}
              </button>
            </div>
          )}

          {/* TAB 3: REGISTER NEW VIRTUAL DUKAAN */}
          {tab === "new" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleRegister({
                  name: newName,
                  owner_name: newOwner,
                  phone: newPhone,
                  language: newLang,
                  pin: newPin,
                });
              }}
              className="space-y-3"
            >
              <div>
                <label className="block text-xs font-bold text-slate-300 mb-1">
                  Virtual Dukaan / Shop Name:
                </label>
                <input
                  required
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Sri Krishna Provision Store"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-300 mb-1">
                  Shopkeeper / Proprietor Name:
                </label>
                <input
                  required
                  type="text"
                  value={newOwner}
                  onChange={(e) => setNewOwner(e.target.value)}
                  placeholder="e.g. Suresh Kumar"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-300 mb-1">
                  10-Digit Mobile Number:
                </label>
                <div className="flex rounded-xl border border-slate-700 bg-slate-950 overflow-hidden focus-within:border-emerald-500">
                  <span className="flex items-center px-3 text-xs font-bold text-slate-400 bg-slate-900 border-r border-slate-800">
                    +91
                  </span>
                  <input
                    required
                    type="tel"
                    maxLength={10}
                    value={newPhone}
                    onChange={(e) => setNewPhone(e.target.value.replace(/[^0-9]/g, ""))}
                    placeholder="9876543210"
                    className="w-full bg-transparent px-3 py-2 text-sm text-white outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs font-bold text-slate-300 mb-1">
                    Language:
                  </label>
                  <select
                    value={newLang}
                    onChange={(e) => setNewLang(e.target.value)}
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-2 py-2 text-xs text-white outline-none focus:border-emerald-500"
                  >
                    {LANGS.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-300 mb-1">
                    4-Digit PIN:
                  </label>
                  <input
                    type="password"
                    maxLength={6}
                    value={newPin}
                    onChange={(e) => setNewPin(e.target.value)}
                    placeholder="1234"
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting || !newName || !newOwner || newPhone.length < 10}
                className="w-full rounded-xl bg-gradient-to-r from-emerald-600 to-emerald-500 py-3 text-sm font-bold text-white shadow-lg shadow-emerald-900/40 transition hover:from-emerald-500 hover:to-emerald-400 disabled:opacity-50 mt-2 active:scale-95"
              >
                {submitting ? "Creating Virtual Dukaan…" : "✨ Create My Virtual Dukaan"}
              </button>
            </form>
          )}

          {/* Quick Info */}
          <div className="mt-5 border-t border-slate-800/80 pt-3 text-center">
            <p className="text-[11px] text-slate-400">
              🔒 Session stays saved on this device. You will not need to authenticate on future visits.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

