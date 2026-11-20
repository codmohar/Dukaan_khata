"use client";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, Customer, inr, Stats, whatsAppReminderUrl } from "@/lib/api";
import { useLive } from "@/lib/supabase";
import { ErrorBanner, PageTitle, Stat } from "@/components/ui";

export default function ReportsPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [shopName, setShopName] = useState("Kirana Store");
  const [stats, setStats] = useState<Stats | null>(null);
  const [waEditId, setWaEditId] = useState<string | null>(null);
  const [waInput, setWaInput] = useState("");
  const [err, setErr] = useState("");

  const loadData = () => {
    api.shop().then((s) => { if (s?.name) setShopName(s.name); }).catch(() => {});
    Promise.all([api.customers(), api.stats()])
      .then(([c, st]) => {
        setCustomers(Array.isArray(c) ? c : []);
        setStats(st);
        setErr("");
      })
      .catch(() => setErr("Could not reach backend API."));
  };

  const handleSaveWa = async (cid: string, e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = waInput.trim();
    if (!cleaned) return;
    try {
      await api.updateCustomer(cid, { phone: cleaned });
      setWaEditId(null);
      setWaInput("");
      loadData();
    } catch (ex) {
      setErr(String(ex));
    }
  };

  useLive(loadData, []);

  // Filter customers who owe money (balance > 0)
  const debtors = (Array.isArray(customers) ? customers : [])
    .map((c) => ({ ...c, bal: Number(c.balance) }))
    .filter((c) => c.bal > 0)
    .sort((a, b) => b.bal - a.bal);

  const totalOutstanding = debtors.reduce((sum, c) => sum + c.bal, 0);
  const weekCredit = (stats?.last_7_days ?? []).reduce((a, d) => a + d.credit, 0);
  const weekPayment = (stats?.last_7_days ?? []).reduce((a, d) => a + d.payment, 0);

  const topDebtorsChart = debtors.slice(0, 8).map((d) => ({
    name: d.name.length > 14 ? d.name.slice(0, 12) + "…" : d.name,
    amount: d.bal,
  }));

  return (
    <>
      <PageTitle
        title="Ledger Analytics & Reports"
        sub="Who owes you, collection efficiency, and customer debt ranking"
      />

      <ErrorBanner msg={err} onClose={() => setErr("")} />

      {/* 4 Stat Cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Total Udhar Owed"
          value={inr(totalOutstanding)}
          tone="red"
          subtext="Total market dues"
        />
        <Stat
          label="Udhar Given (7 Days)"
          value={inr(weekCredit)}
          tone="default"
          subtext="Past week credit"
        />
        <Stat
          label="Cash Collected (7 Days)"
          value={inr(weekPayment)}
          tone="green"
          subtext="Past week payments"
        />
        <Stat
          label="Customers with Dues"
          value={debtors.length}
          tone={debtors.length > 0 ? "amber" : "default"}
          subtext="Pending recovery"
        />
      </div>

      {/* Top 8 Pending Balances Chart */}
      <div className="card mt-6">
        <div className="mb-4">
          <h2 className="font-bold text-slate-900">Top Pending Customer Balances</h2>
          <p className="text-xs text-slate-500">Highest credit dues requiring attention</p>
        </div>

        {debtors.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-400">
            🎉 All customer accounts are clear! No pending udhar dues.
          </div>
        ) : (
          <div style={{ height: Math.max(200, Math.min(topDebtorsChart.length, 8) * 44) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={topDebtorsChart} layout="vertical" margin={{ left: 10, right: 30 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                <XAxis
                  type="number"
                  stroke="#94a3b8"
                  fontSize={12}
                  tickFormatter={(v) => `₹${v}`}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={110}
                  stroke="#64748b"
                  fontSize={12}
                  tickLine={false}
                />
                <Tooltip formatter={(v: number) => [inr(v), "Pending Due"]} />
                <Bar dataKey="amount" name="Owes" fill="#ef4444" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Debtors Recovery Table */}
      <div className="card mt-6 overflow-x-auto !p-0 shadow-sm border border-slate-200">
        <div className="p-4 border-b border-slate-200 flex justify-between items-center">
          <div>
            <h3 className="font-bold text-slate-900">Debtors Recovery List</h3>
            <p className="text-xs text-slate-500">Send instant WhatsApp payment reminders</p>
          </div>
          <span className="text-xs font-semibold text-slate-500">{debtors.length} customers</span>
        </div>

        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50/80 text-xs font-bold uppercase tracking-wider text-slate-500">
            <tr>
              <th className="p-3.5">Customer Name</th>
              <th className="p-3.5">Landmark</th>
              <th className="p-3.5">Phone Number</th>
              <th className="p-3.5 text-right">Pending Balance</th>
              <th className="p-3.5 text-right">Reminder</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {debtors.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-8 text-center text-slate-400">
                  No customers currently owe money.
                </td>
              </tr>
            ) : (
              debtors.map((c) => {
                const hasWa = Boolean(c.phone && c.phone.trim());
                const waUrl = whatsAppReminderUrl(c.phone, c.name, c.bal, shopName);
                return (
                  <tr key={c.id} className="hover:bg-slate-50/70">
                    <td className="p-3.5">
                      <div className="font-bold text-slate-900">{c.name}</div>
                      {!hasWa && (
                        <div className="mt-1">
                          {waEditId === c.id ? (
                            <form onSubmit={(e) => handleSaveWa(c.id, e)} className="flex flex-wrap items-center gap-1">
                              <input
                                type="tel"
                                inputMode="tel"
                                autoFocus
                                required
                                placeholder="10-digit WhatsApp #"
                                value={waInput}
                                onChange={(e) => setWaInput(e.target.value)}
                                className="rounded-lg border border-emerald-400 bg-white px-2 py-0.5 text-xs w-36"
                              />
                              <button className="rounded-lg bg-emerald-600 px-2 py-0.5 text-[11px] font-bold text-white">
                                Save
                              </button>
                              <button
                                type="button"
                                onClick={() => setWaEditId(null)}
                                className="rounded-lg bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600"
                              >
                                Cancel
                              </button>
                            </form>
                          ) : (
                            <button
                              type="button"
                              onClick={() => { setWaEditId(c.id); setWaInput(""); }}
                              className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-300 px-2 py-0.5 text-[10px] font-bold text-emerald-700 hover:bg-emerald-100"
                            >
                              📱 + Add WhatsApp Number
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="p-3.5 text-xs text-slate-500">{c.landmark || "—"}</td>
                    <td className="p-3.5 text-xs text-slate-500">{c.phone || "No phone"}</td>
                    <td className="p-3.5 text-right font-black text-red-600">{inr(c.bal)}</td>
                    <td className="p-3.5 text-right">
                      {hasWa ? (
                        <a
                          href={waUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="btn bg-emerald-50 text-emerald-700 border border-emerald-300 hover:bg-emerald-100 text-xs py-1 px-2.5 inline-flex items-center gap-1 font-semibold"
                        >
                          <span>💬</span>
                          <span>Send Reminder</span>
                        </a>
                      ) : (
                        <span className="text-xs text-slate-400">No phone</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
