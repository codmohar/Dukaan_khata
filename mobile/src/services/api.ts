import "react-native-url-polyfill/auto";
import { createClient } from "@supabase/supabase-js";
import { useEffect, useRef } from "react";
import { API_URL, SUPABASE_KEY, SUPABASE_URL } from "../config";

let currentMobileShopId = "";

export function setMobileShopId(id: string) {
  currentMobileShopId = id;
}

export function getMobileShopId(): string {
  return currentMobileShopId;
}

export type Shop = {
  id: string;
  name: string;
  owner_name?: string | null;
  phone?: string | null;
  language: string;
  pin?: string | null;
};

export type Customer = {
  id: string;
  name: string;
  phone?: string | null;
  landmark?: string | null;
  balance: string | number;
  created_at?: string;
};

export type Txn = {
  id: string;
  customer_id?: string;
  customer_name?: string;
  type: "credit" | "payment";
  amount: string | number;
  note?: string | null;
  status: "draft" | "confirmed" | "cancelled";
  created_at: string;
};

export type Stats = {
  total_outstanding: string | number;
  credit_today: string | number;
  payments_today: string | number;
  customer_count?: number;
  pending_drafts: number;
};

const get = async <T,>(path: string): Promise<T> => {
  const sid = getMobileShopId();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(sid ? { "X-Shop-Id": sid } : {}),
  };
  const r = await fetch(API_URL + path, { headers });
  if (!r.ok) {
    const errorText = await r.text();
    throw new Error(errorText || r.statusText);
  }
  return r.json();
};

const post = async <T,>(path: string, body?: any): Promise<T> => {
  const sid = getMobileShopId();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(sid ? { "X-Shop-Id": sid } : {}),
  };
  const r = await fetch(API_URL + path, {
    method: "POST",
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const errorText = await r.text();
    throw new Error(errorText || r.statusText);
  }
  return r.json();
};

export const api = {
  getShops: () => get<Shop[]>("/auth/shops"),
  login: (body: { phone?: string; pin?: string; shop_id?: string }) =>
    post<{ token: string; shop: Shop; message: string }>("/auth/login", body).then((res) => {
      setMobileShopId(res.token);
      return res;
    }),
  registerShop: (body: { name: string; owner_name: string; phone: string; language?: string; pin?: string }) =>
    post<{ token: string; shop: Shop; message: string }>("/auth/register", body).then((res) => {
      setMobileShopId(res.token);
      return res;
    }),
  authMe: () => get<Shop>("/auth/me"),
  shop: () => get<Shop>("/shop"),
  customers: () => get<Customer[]>("/customers"),
  updateCustomer: async (id: string, body: { name?: string; phone?: string; landmark?: string }) => {
    const sid = getMobileShopId();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(sid ? { "X-Shop-Id": sid } : {}),
    };
    const r = await fetch(`${API_URL}/customers/${id}`, {
      method: "PUT",
      headers,
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  txns: () => get<Txn[]>("/transactions?limit=50"),
  stats: () => get<Stats>("/dashboard/stats"),
  finalize: async (id: string, action: "confirm" | "cancel") => {
    const sid = getMobileShopId();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(sid ? { "X-Shop-Id": sid } : {}),
    };
    const r = await fetch(`${API_URL}/transactions/${id}/${action}`, {
      method: "POST",
      headers,
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
};

export const inr = (n: string | number) =>
  "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });

export const when = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });

export const whatsAppReminderUrl = (
  phone?: string | null,
  name: string = "Customer",
  amount: number = 0,
  shopName: string = "Kirana Store"
) => {
  if (!phone) return "";
  const cleanPhone = phone.replace(/[^0-9]/g, "");
  const targetNumber = cleanPhone.length === 10 ? `91${cleanPhone}` : cleanPhone;
  const message = `Namaste ${name} ji, reminder from ${shopName}: your pending ledger balance is ₹${amount}. Dhanyawad! 🙏`;
  return `https://wa.me/${targetNumber}?text=${encodeURIComponent(message)}`;
};

const supabase = SUPABASE_URL && SUPABASE_KEY ? createClient(SUPABASE_URL, SUPABASE_KEY) : null;

/** Calls `load` now, and again on any realtime change (or polls every 5 s if Supabase isn't configured). */
export function useLive(load: () => void) {
  const ref = useRef(load);
  ref.current = load;

  useEffect(() => {
    const run = () => ref.current();
    run();

    if (!supabase) {
      const t = setInterval(run, 5000);
      return () => clearInterval(t);
    }

    const ch = supabase
      .channel("mobile-live-" + Math.random().toString(36).slice(2))
      .on("postgres_changes", { event: "*", schema: "public", table: "transactions" }, run)
      .on("postgres_changes", { event: "*", schema: "public", table: "customers" }, run)
      .subscribe();

    return () => {
      supabase.removeChannel(ch);
    };
  }, []);
}

// ---------- Image scans ("Scan Book") ----------
export type Candidate = { customer_id: string; name: string; landmark?: string | null };
export type ScanLine = {
  id: string;
  raw_name: string | null;
  customer_id: string | null;
  type: "credit" | "payment";
  amount: string | number;
  confidence: number;
  raw_text: string | null;
  candidates: Candidate[];
  duplicate: boolean;
  include: boolean;
};
export type ScanData = {
  scan: { id: string; summary: string | null; warnings: string[] };
  lines: ScanLine[];
};

async function sc<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API_URL + path, init);
  if (!r.ok) {
    const b = await r.json().catch(() => null);
    const d = b?.detail;
    throw new Error(typeof d === "string" ? d : d?.message ?? r.statusText);
  }
  return r.json();
}

export const scans = {
  upload: (uri: string, hint?: string) => {
    const f = new FormData();
    f.append("file", { uri, name: "scan.jpg", type: "image/jpeg" } as any);
    if (hint) f.append("hint", hint);
    return sc<ScanData>("/scans", { method: "POST", body: f });
  },
  edit: (id: string, patch: Record<string, unknown>) =>
    sc<ScanLine>(`/scans/lines/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  approve: (id: string) => sc<{ created: number }>(`/scans/${id}/approve`, { method: "POST" }),
  reject: (id: string) => sc(`/scans/${id}/reject`, { method: "POST" }),
};
