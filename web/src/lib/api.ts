export function getCurrentShopId(): string {
  if (typeof window !== "undefined") {
    const raw = localStorage.getItem("dukaan_shop_id");
    if (!raw || raw === "undefined" || raw === "null" || raw === "none" || raw.trim() === "") {
      try {
        localStorage.removeItem("dukaan_shop_id");
      } catch {
        // ignore storage error
      }
      return "";
    }
    return raw.trim();
  }
  return "";
}

export function setCurrentShopId(id: string): void {
  if (typeof window !== "undefined") {
    if (id && id !== "undefined" && id !== "null" && id !== "none" && id.trim()) {
      localStorage.setItem("dukaan_shop_id", id.trim());
    } else {
      localStorage.removeItem("dukaan_shop_id");
      localStorage.removeItem("dukaan_shop_data");
    }
  }
}

export function getApiUrl(): string {
  if (typeof window !== "undefined" && window.location) {
    // Same-origin unified proxy when accessed via HTTPS tunnel, Nginx (port 80), or port 4000
    const port = window.location.port;
    if (window.location.protocol === "https:" || port === "4000" || port === "80" || port === "") {
      return `${window.location.origin}/api`;
    }
    const envUrl = process.env.NEXT_PUBLIC_API_URL;
    if (envUrl && !envUrl.includes("localhost") && !envUrl.includes("127.0.0.1")) {
      return envUrl;
    }
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

export function getWsUrl(lang?: string): string {
  const sid = getCurrentShopId();
  let base = "";
  if (typeof window !== "undefined" && window.location) {
    const port = window.location.port;
    if (window.location.protocol === "https:" || port === "4000" || port === "80" || port === "") {
      const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
      base = `${wsProto}//${window.location.host}/ws/voice`;
    }
  }
  if (!base) {
    base = getApiUrl().replace(/^http/, "ws") + "/ws/voice";
  }
  const params = new URLSearchParams();
  if (lang) params.set("language", lang);
  if (sid) params.set("shop_id", sid);
  const q = params.toString();
  return q ? `${base}?${q}` : base;
}

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = API.replace(/^http/, "ws") + "/ws/voice";

export type Customer = {
  id: string;
  name: string;
  phone?: string | null;
  landmark?: string | null;
  balance: string | number;
  outstanding_balance?: string | number;
  created_at?: string;
  recent_transactions?: Txn[];
};

export type HouseholdMember = {
  id: string;
  customer_id: string;
  shop_id: string;
  member_name: string;
  relationship?: string | null;
  is_authorized: boolean;
  created_at: string;
};

export type ShopRule = {
  id: string;
  shop_id: string;
  rule_category: "NEW_CUSTOMER_CAP" | "BALANCE_CAP" | "TIME_CUTOFF" | "FREQUENCY_CAP" | "DISALLOW_MEMBER_CREDIT";
  rule_text: string;
  structured_condition: Record<string, any>;
  is_active: boolean;
  created_at: string;
};

export type PromiseItem = {
  id: string;
  shop_id: string;
  customer_id?: string | null;
  member_id?: string | null;
  entity_name: string;
  promise_type: "PAYMENT_PROMISE" | "GOODS_RESERVATION" | "SUPPLIER_DELIVERY";
  promised_amount?: number | null;
  description: string;
  expected_date: string;
  status: "PENDING" | "FULFILLED" | "OVERDUE" | "CANCELLED";
  fulfilled_transaction_id?: string | null;
  source_transcript?: string | null;
  created_at: string;
  fulfilled_at?: string | null;
};

export type PromisesSummary = {
  due_today: number;
  overdue: number;
  total_pending_amount: number;
  items: PromiseItem[];
};

export type TimelineEvent = {
  transaction_id: string;
  occurred_at: string;
  type: "credit" | "payment" | "adjustment";
  amount: number;
  payment_mode?: string | null;
  member_id?: string | null;
  member_name?: string | null;
  item_note?: string | null;
  transcript_snippet?: string | null;
  rule_override: boolean;
  balance_after: number;
};

export type DisputeTimeline = {
  customer_id: string;
  customer_name: string;
  phone?: string | null;
  landmark?: string | null;
  current_balance: number;
  computed_final_balance: number;
  balance_mismatch: boolean;
  timeline: TimelineEvent[];
};

export type DailyReconciliationItem = {
  id: string;
  shop_id: string;
  reconciliation_date: string;
  recorded_cash: number;
  actual_cash: number;
  recorded_upi: number;
  actual_upi: number;
  cash_difference: number;
  upi_difference: number;
  status: "MATCHED" | "NEEDS_INVESTIGATION" | "RESOLVED";
  findings: Array<{ kind: string; message: string; [key: string]: any }>;
  audit_notes?: string | null;
  created_at: string;
};

export type Txn = {
  id: string;
  customer_id: string;
  customer_name?: string;
  customer_phone?: string;
  member_id?: string | null;
  member_name?: string | null;
  type: "credit" | "payment" | "adjustment";
  amount: string | number;
  payment_mode?: "cash" | "upi" | "credit" | "other" | null;
  adjustment_reason?: "discount" | "return" | "write_off" | "correction" | null;
  due_date?: string | null;
  backdated_to?: string | null;
  items?: { name?: string; qty?: string; amount?: number }[] | null;
  item_note?: string | null;
  rule_warnings?: Array<{ rule_category: string; message: string; [key: string]: any }>;
  requires_override?: boolean;
  rule_override?: boolean;
  transcript_snippet?: string | null;
  note?: string | null;
  status: "draft" | "confirmed" | "cancelled";
  created_at: string;
  confirmed_at?: string | null;
};

export type Stats = {
  total_outstanding: string | number;
  credit_today: string | number;
  payments_today: string | number;
  customer_count: number;
  pending_drafts: number;
  last_7_days: { date: string; credit: number; payment: number }[];
};

export type Shop = {
  id: string;
  name: string;
  owner_name?: string | null;
  phone?: string | null;
  language: string;
  pin?: string | null;
};

export type ReportsSummary = {
  debtors: { id: string; name: string; phone?: string | null; landmark?: string | null; balance: number }[];
  total_outstanding: number;
  debtors_count: number;
  credit_30d: number;
  payment_30d: number;
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const sid = getCurrentShopId();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(sid ? { "X-Shop-Id": sid } : {}),
    ...((init?.headers as Record<string, string>) || {}),
  };

  const r = await fetch(getApiUrl() + path, {
    ...init,
    headers,
  });
  if (!r.ok) {
    const errorText = await r.text();
    throw new Error(errorText || r.statusText);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}

const qs = (o: Record<string, string | undefined>) => {
  const p = new URLSearchParams(
    Object.entries(o).filter(([, v]) => v !== undefined && v !== "") as [string, string][]
  ).toString();
  return p ? "?" + p : "";
};

let shopCache: Shop | null = null;
let shopPromise: Promise<Shop> | null = null;

export const api = {
  health: () => call<{ ok: boolean; database?: boolean; default_shop_id?: string }>("/health"),
  // Virtual Dukaan Authentication & Multi-Tenancy
  getShops: () => call<Shop[]>("/auth/shops"),
  login: (body: { phone?: string; pin?: string; shop_id?: string }) =>
    call<{ token: string; shop: Shop; message: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    }).then((res) => {
      setCurrentShopId(res.token);
      shopCache = res.shop;
      return res;
    }),
  registerShop: (body: { name: string; owner_name: string; phone: string; language?: string; pin?: string }) =>
    call<{ token: string; shop: Shop; message: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    }).then((res) => {
      setCurrentShopId(res.token);
      shopCache = res.shop;
      return res;
    }),
  authMe: () => call<Shop>("/auth/me"),
  logout: () => {
    setCurrentShopId("");
    shopCache = null;
    shopPromise = null;
  },
  shop: () => {
    if (shopCache) return Promise.resolve(shopCache);
    if (!shopPromise) {
      shopPromise = call<Shop>("/shop")
        .then((s) => {
          shopCache = s;
          return s;
        })
        .finally(() => {
          shopPromise = null;
        });
    }
    return shopPromise;
  },
  updateShop: (s: Partial<Shop>) =>
    call<Shop>("/shop", { method: "PUT", body: JSON.stringify(s) }).then((updated) => {
      shopCache = updated;
      return updated;
    }),
  stats: () => call<Stats>("/dashboard/stats"),
  reportsSummary: () => call<ReportsSummary>("/reports/summary"),
  customers: (q?: string) => call<Customer[]>("/customers" + qs({ q })),
  customer: (id: string) => call<Customer>(`/customers/${id}`),
  addCustomer: (c: { name: string; phone?: string; landmark?: string }) =>
    call<Customer>("/customers", { method: "POST", body: JSON.stringify(c) }),
  updateCustomer: (id: string, c: { name?: string; phone?: string; landmark?: string }) =>
    call<Customer>(`/customers/${id}`, { method: "PUT", body: JSON.stringify(c) }),
  deleteCustomer: (id: string) => call<void>(`/customers/${id}`, { method: "DELETE" }),
  txns: (f: Record<string, string | undefined> = {}) => call<Txn[]>("/transactions" + qs(f)),
  addTxn: (t: {
    customer_id: string;
    type: "credit" | "payment" | "adjustment";
    amount: number;
    payment_mode?: "cash" | "upi" | "other";
    adjustment_reason?: "discount" | "return" | "write_off" | "correction";
    note?: string;
    status?: string;
  }) => call<Txn>("/transactions", { method: "POST", body: JSON.stringify(t) }),
  finalize: (id: string, action: "confirm" | "cancel", override_warnings: boolean = false) =>
    call<{ status: string; draft_id?: string; new_balance?: number }>(`/transactions/${id}/${action}`, {
      method: "POST",
      body: JSON.stringify({ override_warnings }),
    }),
  // Household Khata
  household: (customerId: string) => call<HouseholdMember[]>(`/customers/${customerId}/household`),
  addHouseholdMember: (customerId: string, m: { member_name: string; relationship?: string; is_authorized?: boolean }) =>
    call<HouseholdMember>(`/customers/${customerId}/household`, { method: "POST", body: JSON.stringify(m) }),
  deleteHouseholdMember: (customerId: string, memberId: string) =>
    call<void>(`/customers/${customerId}/household/${memberId}`, { method: "DELETE" }),
  // Shop Rules
  rules: () => call<ShopRule[]>("/rules"),
  addRule: (r: { rule_category: string; rule_text: string; structured_condition: any }) =>
    call<ShopRule>("/rules", { method: "POST", body: JSON.stringify(r) }),
  toggleRule: (ruleId: string, is_active: boolean) =>
    call<ShopRule>(`/rules/${ruleId}`, { method: "PATCH", body: JSON.stringify({ is_active }) }),
  deleteRule: (ruleId: string) => call<void>(`/rules/${ruleId}`, { method: "DELETE" }),
  // Promises
  promises: (f: { status?: string; customer_id?: string } = {}) => call<PromiseItem[]>("/promises" + qs(f)),
  promisesSummary: () => call<PromisesSummary>("/promises/summary"),
  updatePromise: (id: string, patch: { expected_date?: string; status?: string }) =>
    call<PromiseItem>(`/promises/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  // Memory & Search
  memorySearch: (q: string) => call<{ query: string; results: Array<{ source: string; [key: string]: any }> }>("/memory/search" + qs({ q })),
  // Dispute Timeline
  timeline: (customerId: string, memberId?: string) =>
    call<DisputeTimeline>(`/customers/${customerId}/timeline` + qs({ member_id: memberId })),
  // Daily Reconciliation
  startReconciliation: () =>
    call<{ recorded_cash: number; recorded_upi: number; cash_count: number; upi_count: number; date: string }>("/reconciliation/start", { method: "POST" }),
  runReconciliation: (body: { actual_cash: number; actual_upi: number; notes?: string }) =>
    call<DailyReconciliationItem>("/reconciliation/run", { method: "POST", body: JSON.stringify(body) }),
  reconciliations: () => call<DailyReconciliationItem[]>("/reconciliation"),
  resolveReconciliation: (id: string, resolution_note: string) =>
    call<DailyReconciliationItem>(`/reconciliation/${id}/resolve`, { method: "POST", body: JSON.stringify({ resolution_note }) }),
  processVoice: (body: { text?: string; audio_base64?: string; language?: string }) =>
    call<{ transcript: string; reply: string; audio_base64?: string; events: any[] }>("/voice/process", {
      method: "POST",
      body: JSON.stringify(body),
    }),
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

export const whatsAppReminderUrl = (phone?: string | null, name: string = "Customer", amount: number = 0, shopName: string = "Dukaan") => {
  if (!phone) return "";
  const cleanPhone = phone.replace(/[^0-9]/g, "");
  const targetNumber = cleanPhone.length === 10 ? `91${cleanPhone}` : cleanPhone;
  const message = `Namaste ${name} ji, this is a friendly reminder from ${shopName}. Your pending khata balance is ₹${amount}. Please clear at your convenience. Dhanyawad! 🙏`;
  return `https://wa.me/${targetNumber}?text=${encodeURIComponent(message)}`;
};

// ---------- Image scans ("Scan Book") ----------
export type Candidate = { customer_id: string; name: string; landmark?: string | null; score: number };
export type ScanLine = {
  id: string;
  raw_name: string | null;
  customer_id: string | null;
  type: "credit" | "payment";
  amount: string | number;
  txn_date: string | null;
  note: string | null;
  confidence: number;
  raw_text: string | null;
  candidates: Candidate[];
  duplicate: boolean;
  include: boolean;
  transaction_id?: string | null;
};
export type ScanData = {
  scan: {
    id: string;
    doc_type: string;
    summary: string | null;
    total_shown: string | number | null;
    warnings: string[];
    status: string;
  };
  lines: ScanLine[];
};

async function scanCall<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getApiUrl();
  const sid = getCurrentShopId();
  const headers = {
    ...(sid ? { "X-Shop-Id": sid } : {}),
    ...(init?.headers || {}),
  };
  const r = await fetch(base + path, { ...init, headers });
  if (!r.ok) {
    const b = await r.json().catch(() => null);
    const d = b?.detail;
    throw new Error(typeof d === "string" ? d : d?.message ?? r.statusText);
  }
  return r.json();
}

export const scans = {
  upload: (file: Blob, hint?: string, autoCommit: boolean = true) => {
    const f = new FormData();
    f.append("file", file, "scan.jpg");
    if (hint) f.append("hint", hint);
    if (autoCommit) f.append("auto_commit", "true");
    return scanCall<ScanData>(`/scans?commit_now=${autoCommit ? "true" : "false"}`, { method: "POST", body: f });
  },
  editLine: (id: string, patch: Record<string, unknown>) =>
    scanCall<ScanLine>(`/scans/lines/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  approve: (id: string, autoCreateCustomers: boolean = true) =>
    scanCall<{ created: number }>(`/scans/${id}/approve?auto_create_customers=${autoCreateCustomers ? "true" : "false"}`, { method: "POST" }),
  reject: (id: string) => scanCall(`/scans/${id}/reject`, { method: "POST" }),
};
