"use client";
import { useState } from "react";
import Link from "next/link";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, inr, when, Stats, Txn, Shop, PromiseItem, PromisesSummary, DailyReconciliationItem } from "@/lib/api";
import { useLive } from "@/lib/supabase";
import { Badge, ErrorBanner, Modal, PageTitle, Stat } from "@/components/ui";

export default function Dashboard() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [recent, setRecent] = useState<Txn[]>([]);
  const [err, setErr] = useState("");
  const [drafts, setDrafts] = useState<Txn[]>([]);

  // Promises & Reconciliation state
  const [promisesSum, setPromisesSum] = useState<PromisesSummary>({
    due_today: 0,
    overdue: 0,
    total_pending_amount: 0,
    items: [],
  });
  const [reconciledToday, setReconciledToday] = useState(false);
  const [recModalOpen, setRecModalOpen] = useState(false);
  const [recStep, setRecStep] = useState<1 | 2 | 3>(1);
  const [recLoading, setRecLoading] = useState(false);
  const [recRecorded, setRecRecorded] = useState<{ recorded_cash: number; recorded_upi: number } | null>(null);
  const [actualCashInput, setActualCashInput] = useState("");
  const [actualUpiInput, setActualUpiInput] = useState("");
  const [recResult, setRecResult] = useState<DailyReconciliationItem | null>(null);

  const loadData = () => {
    Promise.all([
      api.shop().catch(() => null),
      api.stats(),
      api.txns({ limit: "8" }),
      api.txns({ status: "draft", limit: "5" }),
      api.promisesSummary().catch(() => ({ due_today: 0, overdue: 0, total_pending_amount: 0, items: [] })),
      api.reconciliations().catch(() => []),
    ])
      .then(([sh, s, tx, dr, pSum, recs]) => {
        if (sh) setShop(sh);
        setStats(s);
        setRecent(Array.isArray(tx) ? tx : []);
        setDrafts(Array.isArray(dr) ? dr : []);
        setPromisesSum(
          pSum && typeof pSum === "object"
            ? pSum
            : { due_today: 0, overdue: 0, total_pending_amount: 0, items: [] }
        );
        const todayStr = new Date().toISOString().slice(0, 10);
        setReconciledToday(
          Array.isArray(recs) &&
            recs.some((r) => r.reconciliation_date === todayStr && r.status === "MATCHED")
        );
        setErr("");
      })
      .catch(() => setErr("Could not reach backend API. Check if DukaanAI backend is running on port 8000."));
  };

  useLive(loadData, []);

  const startReconciliationFlow = async () => {
    setRecLoading(true);
    try {
      const rec = await api.startReconciliation();
      setRecRecorded({ recorded_cash: rec.recorded_cash, recorded_upi: rec.recorded_upi });
      setActualCashInput(String(rec.recorded_cash || ""));
      setActualUpiInput(String(rec.recorded_upi || ""));
      setRecStep(1);
      setRecResult(null);
      setRecModalOpen(true);
    } catch (e: any) {
      setErr("Failed to start reconciliation: " + e.message);
    } finally {
      setRecLoading(false);
    }
  };

  const handleRunReconciliation = async () => {
    setRecLoading(true);
    try {
      const res = await api.runReconciliation({
        actual_cash: Number(actualCashInput) || 0,
        actual_upi: Number(actualUpiInput) || 0,
      });
      setRecResult(res);
      setRecStep(3);
      if (res.status === "MATCHED") {
        setReconciledToday(true);
      }
    } catch (e: any) {
      setErr("Failed to run reconciliation: " + e.message);
    } finally {
      setRecLoading(false);
    }
  };

  const handleAction = async (id: string, action: "confirm" | "cancel") => {
    try {
      await api.finalize(id, action);
      loadData();
    } catch (e) {
      setErr(String(e));
    }
  };

  const chartData = (stats?.last_7_days ?? []).map((d) => ({
    ...d,
    day: new Date(d.date).toLocaleDateString("en-IN", { weekday: "short", day: "numeric" }),
  }));

  const shopGreeting = shop?.owner_name
    ? `Namaste, ${shop.owner_name} 🙏`
    : shop?.name
    ? `Namaste, ${shop.name} 🙏`
    : "Namaste, Shopkeeper 🙏";

  const shopSub = shop?.name
    ? `${shop.name} • Live Ledger & Voice Sync`
    : "Kirana khata overview & real-time sync";

  return (
    <>
      <PageTitle title={shopGreeting} sub={shopSub}>
        <Link
          href="/voice"
          className="btn bg-emerald-600 text-white hover:bg-emerald-700 shadow-md flex items-center gap-2"
        >
          <span>🎙️</span>
          <span>Voice Khata</span>
        </Link>
      </PageTitle>

      <ErrorBanner msg={err} onClose={() => setErr("")} />

      {/* 5 Key Stat Cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Stat
          label="Total Udhar Dues"
          value={inr(stats?.total_outstanding ?? 0)}
          tone="red"
          subtext="Net pending balance"
        />
        <Stat
          label="Udhar Today"
          value={inr(stats?.credit_today ?? 0)}
          tone="default"
          subtext="Today's credit given"
        />
        <Stat
          label="Received Today"
          value={inr(stats?.payments_today ?? 0)}
          tone="green"
          subtext="Cash/UPI payments"
        />
        <Stat
          label="Active Customers"
          value={stats?.customer_count ?? 0}
          subtext="Registered in shop"
        />
        <Stat
          label="Awaiting Confirm"
          value={stats?.pending_drafts ?? 0}
          tone={stats?.pending_drafts ? "amber" : "default"}
          subtext="Unconfirmed drafts"
        />
      </div>

      {/* Today's Promises & Alerts Card */}
      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <span className="text-xl">🤝</span>
            <div>
              <h2 className="text-base font-bold text-slate-900">Today&apos;s Promises &amp; Evening Reconciliation</h2>
              <p className="text-xs text-slate-500">Track payment commitments and daily cash/UPI balance check</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {(promisesSum?.overdue ?? 0) > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full bg-red-100 text-red-800 border border-red-300 px-2.5 py-0.5 text-xs font-bold">
                ⚠️ {promisesSum.overdue} Overdue
              </span>
            )}
            <button
              onClick={startReconciliationFlow}
              disabled={recLoading}
              className={`btn text-xs font-bold px-3.5 py-2 shadow-sm flex items-center gap-1.5 ${
                reconciledToday
                  ? "bg-emerald-50 text-emerald-700 border border-emerald-300 hover:bg-emerald-100"
                  : "bg-emerald-600 text-white hover:bg-emerald-700"
              }`}
            >
              <span>{reconciledToday ? "✓" : "📊"}</span>
              <span>{reconciledToday ? "Reconciled Today ✓" : "Start Evening Reconciliation"}</span>
            </button>
          </div>
        </div>

        {(!promisesSum?.items || promisesSum.items.length === 0) ? (
          <p className="text-xs text-slate-400 py-2">No payment promises or deliveries due today. All caught up!</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {promisesSum.items.slice(0, 5).map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between p-3 rounded-xl border border-blue-100 bg-blue-50/50 hover:bg-blue-50 transition"
              >
                <div>
                  <p className="text-xs font-bold text-slate-900">{p.entity_name}</p>
                  <p className="text-[11px] text-slate-500 truncate max-w-[160px]">{p.description}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs font-extrabold text-blue-700">
                    {p.promised_amount ? inr(p.promised_amount) : "Reserved"}
                  </p>
                  <span className="text-[10px] font-semibold text-slate-400 capitalize">
                    {p.promise_type ? p.promise_type.replace(/_/g, " ").toLowerCase() : "promise"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pending Drafts Notice (Actionable) */}
      {drafts.length > 0 && (
        <div className="mt-6 rounded-2xl border-2 border-amber-300 bg-amber-50/80 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="flex h-3 w-3 rounded-full bg-amber-500 animate-ping" />
              <h2 className="text-base font-bold text-amber-900">
                {drafts.length} Voice Draft(s) Awaiting Confirmation
              </h2>
            </div>
            <span className="text-xs font-semibold text-amber-700 uppercase tracking-wider">
              Verify Before Committing
            </span>
          </div>
          <div className="space-y-2">
            {drafts.map((d) => (
              <div
                key={d.id}
                className="flex flex-wrap items-center justify-between rounded-xl bg-white p-3.5 shadow-sm border border-amber-200"
              >
                <div>
                  <p className="font-bold text-slate-900">
                    {d.customer_name}{" "}
                    <span className={d.type === "credit" ? "text-red-600" : "text-emerald-600"}>
                      {d.type === "credit" ? "owes" : "paid"} {inr(d.amount)}
                    </span>
                  </p>
                  <p className="text-xs text-slate-500">{when(d.created_at)} {d.note ? `· ${d.note}` : ""}</p>
                </div>
                <div className="flex items-center gap-2 mt-2 sm:mt-0">
                  <button
                    onClick={() => handleAction(d.id, "confirm")}
                    className="btn bg-emerald-600 text-white text-xs px-3 py-1.5 hover:bg-emerald-700"
                  >
                    ✓ Confirm
                  </button>
                  <button
                    onClick={() => handleAction(d.id, "cancel")}
                    className="btn bg-white text-red-600 border border-red-200 text-xs px-3 py-1.5 hover:bg-red-50"
                  >
                    ✕ Discard
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 7-day BarChart */}
      <div className="card mt-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="font-bold text-slate-900">Last 7 Days Ledger Activity</h2>
            <p className="text-xs text-slate-500">Daily breakdown of Udhar given vs Payments received</p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <span className="flex items-center gap-1.5 font-medium text-red-600">
              <span className="h-3 w-3 rounded-sm bg-red-500" /> Udhar (Credit)
            </span>
            <span className="flex items-center gap-1.5 font-medium text-emerald-600">
              <span className="h-3 w-3 rounded-sm bg-emerald-600" /> Received (Payment)
            </span>
          </div>
        </div>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
              <XAxis dataKey="day" stroke="#94a3b8" fontSize={12} tickLine={false} />
              <YAxis
                stroke="#94a3b8"
                fontSize={12}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `₹${v}`}
              />
              <Tooltip
                formatter={(v: number) => [inr(v), "Amount"]}
                contentStyle={{ borderRadius: "12px", border: "1px solid #e2e8f0" }}
              />
              <Bar dataKey="credit" name="Udhar" fill="#ef4444" radius={[6, 6, 0, 0]} />
              <Bar dataKey="payment" name="Received" fill="#10b981" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent Transactions List */}
      <div className="card mt-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="font-bold text-slate-900">Recent Ledger Entries</h2>
            <p className="text-xs text-slate-500">Live multi-device synced stream</p>
          </div>
          <Link href="/transactions" className="text-sm font-semibold text-emerald-600 hover:underline">
            View All →
          </Link>
        </div>

        {recent.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-400">
            No transactions yet. Click &quot;Voice Khata&quot; to speak your first entry!
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {recent.map((t) => (
              <div key={t.id} className="flex items-center justify-between py-3">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-semibold text-slate-900">{t.customer_name || "Unknown Customer"}</p>
                    <Badge status={t.status === "confirmed" ? t.type : t.status} />
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {when(t.created_at)} {t.note ? `· ${t.note}` : ""}
                  </p>
                </div>
                <div className="text-right">
                  <p
                    className={`text-base font-bold ${
                      t.type === "credit" ? "text-red-600" : "text-emerald-600"
                    }`}
                  >
                    {t.type === "credit" ? "+" : "−"}
                    {inr(t.amount)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 3-Step Evening Reconciliation Modal */}
      <Modal open={recModalOpen} onClose={() => setRecModalOpen(false)} title="Daily Khata Reconciliation">
        <div className="p-1 space-y-4">
          <p className="text-xs text-slate-500">
            End-of-day check: physical cash and UPI collected vs recorded khata ledger entries.
          </p>

          <div className="flex items-center justify-between border-b pb-2 text-xs font-bold text-slate-500">
            <span className={recStep === 1 ? "text-emerald-600 font-extrabold" : ""}>1. Cash Count</span>
            <span>→</span>
            <span className={recStep === 2 ? "text-emerald-600 font-extrabold" : ""}>2. UPI Count</span>
            <span>→</span>
            <span className={recStep === 3 ? "text-emerald-600 font-extrabold" : ""}>3. Comparison &amp; Result</span>
          </div>

          {recStep === 1 && (
            <div className="space-y-3">
              <div className="rounded-xl bg-slate-50 border p-3">
                <span className="text-xs text-slate-500 font-medium">Recorded Cash in DukaanAI Today:</span>
                <p className="text-xl font-black text-slate-900 mt-0.5">{inr(recRecorded?.recorded_cash ?? 0)}</p>
              </div>
              <div>
                <label className="text-xs font-bold text-slate-700 block mb-1">
                  How much physical cash did you collect today? (₹)
                </label>
                <input
                  type="number"
                  inputMode="decimal"
                  autoFocus
                  value={actualCashInput}
                  onChange={(e) => setActualCashInput(e.target.value)}
                  placeholder="0.00"
                  className="w-full rounded-xl border border-slate-300 p-3 text-lg font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setRecModalOpen(false)}
                  className="btn bg-slate-100 text-slate-600 px-4 py-2 text-xs font-bold hover:bg-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => setRecStep(2)}
                  className="btn bg-emerald-600 text-white px-4 py-2 text-xs font-bold hover:bg-emerald-700"
                >
                  Next: UPI Count →
                </button>
              </div>
            </div>
          )}

          {recStep === 2 && (
            <div className="space-y-3">
              <div className="rounded-xl bg-slate-50 border p-3">
                <span className="text-xs text-slate-500 font-medium">Recorded UPI in DukaanAI Today:</span>
                <p className="text-xl font-black text-slate-900 mt-0.5">{inr(recRecorded?.recorded_upi ?? 0)}</p>
              </div>
              <div>
                <label className="text-xs font-bold text-slate-700 block mb-1">
                  Total UPI received today from statements / QR app? (₹)
                </label>
                <input
                  type="number"
                  inputMode="decimal"
                  autoFocus
                  value={actualUpiInput}
                  onChange={(e) => setActualUpiInput(e.target.value)}
                  placeholder="0.00"
                  className="w-full rounded-xl border border-slate-300 p-3 text-lg font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              <div className="flex justify-between gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setRecStep(1)}
                  className="btn bg-slate-100 text-slate-600 px-4 py-2 text-xs font-bold hover:bg-slate-200"
                >
                  ← Back
                </button>
                <button
                  type="button"
                  onClick={handleRunReconciliation}
                  disabled={recLoading}
                  className="btn bg-emerald-600 text-white px-5 py-2 text-xs font-bold hover:bg-emerald-700"
                >
                  {recLoading ? "Analyzing..." : "Reconcile Now ✓"}
                </button>
              </div>
            </div>
          )}

          {recStep === 3 && recResult && (
            <div className="space-y-3">
              <div
                className={`rounded-xl border p-4 text-center ${
                  recResult.status === "MATCHED"
                    ? "bg-emerald-50 border-emerald-300 text-emerald-900"
                    : "bg-amber-50 border-amber-300 text-amber-900"
                }`}
              >
                <span className="text-2xl">{recResult.status === "MATCHED" ? "🎉" : "⚠️"}</span>
                <p className="text-base font-extrabold mt-1">
                  {recResult.status === "MATCHED" ? "Everything Matched Perfectly!" : "Differences Detected"}
                </p>
                <p className="text-xs mt-0.5">
                  Cash Difference: <b>{inr(recResult.cash_difference)}</b> | UPI Difference:{" "}
                  <b>{inr(recResult.upi_difference)}</b>
                </p>
              </div>

              {recResult.findings && recResult.findings.length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-3">
                  <p className="text-xs font-bold text-amber-900 mb-1.5 uppercase">AI Diagnostic Findings:</p>
                  <ul className="list-disc pl-4 space-y-1 text-xs text-slate-700">
                    {recResult.findings.map((f, i) => (
                      <li key={i}>{f.message}</li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-[11px] text-slate-400 bg-slate-50 border border-slate-200 rounded-lg p-2.5">
                ℹ️ Reconciliation covers khata payments only; cash sales not recorded in DukaanAI are excluded.
                Customer balances and transactions are never auto-altered.
              </p>

              <div className="flex justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setRecModalOpen(false)}
                  className="btn bg-emerald-600 text-white px-5 py-2 text-xs font-bold hover:bg-emerald-700"
                >
                  Done
                </button>
              </div>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}
