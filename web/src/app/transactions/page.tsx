"use client";
import { useState } from "react";
import { api, Customer, inr, Txn, when } from "@/lib/api";
import { useLive } from "@/lib/supabase";
import { Badge, ErrorBanner, Modal, PageTitle } from "@/components/ui";

export default function TransactionsPage() {
  const [rows, setRows] = useState<Txn[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [filters, setFilters] = useState({
    type: "",
    status: "",
    start: "",
    end: "",
  });
  const [err, setErr] = useState("");

  // Manual Transaction Modal State
  const [modalOpen, setModalOpen] = useState(false);
  const [manualForm, setManualForm] = useState<{
    customer_id: string;
    type: "credit" | "payment";
    amount: string;
    note: string;
  }>({
    customer_id: "",
    type: "credit",
    amount: "",
    note: "",
  });

  const loadData = () => {
    Promise.all([
      api.txns({ ...filters, limit: "250" }),
      api.customers(),
    ])
      .then(([tx, cust]) => {
        setRows(Array.isArray(tx) ? tx : []);
        setCustomers(Array.isArray(cust) ? cust : []);
        setErr("");
      })
      .catch(() => setErr("Could not reach backend API."));
  };

  useLive(loadData, [filters]);

  const handleAction = async (id: string, action: "confirm" | "cancel") => {
    try {
      await api.finalize(id, action);
      loadData();
    } catch (e) {
      setErr(String(e));
    }
  };

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualForm.customer_id || !manualForm.amount) return;
    try {
      await api.addTxn({
        customer_id: manualForm.customer_id,
        type: manualForm.type,
        amount: parseFloat(manualForm.amount),
        note: manualForm.note || undefined,
        status: "confirmed",
      });
      setModalOpen(false);
      setManualForm({ customer_id: "", type: "credit", amount: "", note: "" });
      loadData();
    } catch (e) {
      setErr(String(e));
    }
  };

  const exportCSV = () => {
    if (rows.length === 0) return;
    const headers = ["Date", "Customer", "Type", "Amount", "Status", "Note"];
    const csvContent =
      "data:text/csv;charset=utf-8," +
      [
        headers.join(","),
        ...rows.map((r) =>
          [
            `"${r.created_at}"`,
            `"${r.customer_name || ""}"`,
            `"${r.type}"`,
            r.amount,
            `"${r.status}"`,
            `"${r.note || ""}"`,
          ].join(",")
        ),
      ].join("\n");

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `dukaan_ledger_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <>
      <PageTitle title="Digital Khata Ledger" sub="Filterable multi-device ledger entries">
        <button
          onClick={exportCSV}
          className="btn bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 text-xs py-2"
        >
          📥 Export CSV
        </button>
        <button
          onClick={() => setModalOpen(true)}
          className="btn bg-emerald-600 text-white hover:bg-emerald-700 text-xs py-2 shadow-sm"
        >
          + Manual Entry
        </button>
      </PageTitle>

      <ErrorBanner msg={err} onClose={() => setErr("")} />

      {/* Filter Controls Bar */}
      <div className="card mb-4 !p-4 bg-white shadow-sm flex flex-wrap gap-2.5 items-center">
        <select
          className="input !w-auto bg-slate-50 text-xs font-semibold"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
        >
          <option value="">All Types (Udhar, Payments &amp; Adjustments)</option>
          <option value="credit">Udhar (Credit)</option>
          <option value="payment">Jama (Payments)</option>
          <option value="adjustment">Adjustments (Return / Discount / Write-off)</option>
        </select>

        <select
          className="input !w-auto bg-slate-50 text-xs font-semibold"
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        >
          <option value="">All Statuses</option>
          <option value="confirmed">Confirmed</option>
          <option value="draft">Awaiting Confirm (Draft)</option>
          <option value="cancelled">Cancelled</option>
        </select>

        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <span>From:</span>
          <input
            type="date"
            className="input !w-auto bg-slate-50 text-xs"
            value={filters.start}
            onChange={(e) => setFilters({ ...filters, start: e.target.value })}
          />
        </div>

        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <span>To:</span>
          <input
            type="date"
            className="input !w-auto bg-slate-50 text-xs"
            value={filters.end}
            onChange={(e) => setFilters({ ...filters, end: e.target.value })}
          />
        </div>

        {(filters.type || filters.status || filters.start || filters.end) && (
          <button
            className="btn bg-slate-100 text-slate-600 hover:bg-slate-200 text-xs py-1.5 px-3"
            onClick={() => setFilters({ type: "", status: "", start: "", end: "" })}
          >
            Clear Filters
          </button>
        )}
      </div>

      {/* Ledger Table */}
      <div className="card overflow-x-auto !p-0 shadow-sm border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50/80 border-b border-slate-200 text-xs font-bold uppercase tracking-wider text-slate-500">
            <tr>
              <th className="p-3.5">Date & Time</th>
              <th className="p-3.5">Customer Name</th>
              <th className="p-3.5">Transaction Type</th>
              <th className="p-3.5 text-right">Amount</th>
              <th className="p-3.5">Note</th>
              <th className="p-3.5">Status</th>
              <th className="p-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-12 text-center text-slate-400">
                  No ledger entries match the selected filters.
                </td>
              </tr>
            ) : (
              rows.map((t) => (
                <tr key={t.id} className="hover:bg-slate-50/70 transition">
                  <td className="whitespace-nowrap p-3.5 text-xs text-slate-500">
                    <div>{when(t.created_at)}</div>
                    {t.backdated_to && (
                      <div className="text-[10px] font-semibold text-slate-400">⏪ Dated: {t.backdated_to}</div>
                    )}
                    {t.due_date && (
                      <div className="text-[10px] font-semibold text-amber-700">📅 Due: {t.due_date}</div>
                    )}
                  </td>
                  <td className="p-3.5 font-bold text-slate-900">{t.customer_name || "—"}</td>
                  <td className="p-3.5">
                    <div className="flex flex-wrap items-center gap-1">
                      <Badge status={t.type} />
                      {t.payment_mode && (
                        <span className="rounded-full bg-blue-100 text-blue-800 px-2 py-0.5 text-[10px] font-bold uppercase">
                          {t.payment_mode}
                        </span>
                      )}
                      {t.adjustment_reason && (
                        <span className="rounded-full bg-purple-100 text-purple-800 px-2 py-0.5 text-[10px] font-bold capitalize">
                          {t.adjustment_reason.replace("_", " ")}
                        </span>
                      )}
                    </div>
                  </td>
                  <td
                    className={`p-3.5 text-right font-black ${
                      t.type === "credit"
                        ? "text-red-600"
                        : t.type === "adjustment"
                        ? "text-purple-700"
                        : "text-emerald-600"
                    }`}
                  >
                    {t.type === "credit" ? "+" : "−"}{inr(t.amount)}
                  </td>
                  <td className="p-3.5 text-xs text-slate-500 max-w-xs truncate">{t.note || "—"}</td>
                  <td className="p-3.5">
                    <Badge status={t.status} />
                  </td>
                  <td className="whitespace-nowrap p-3.5 text-right">
                    {t.status === "draft" && (
                      <div className="flex justify-end gap-1.5">
                        <button
                          className="btn bg-emerald-600 text-white hover:bg-emerald-700 text-xs py-1 px-2.5"
                          onClick={() => handleAction(t.id, "confirm")}
                        >
                          ✓ Confirm
                        </button>
                        <button
                          className="btn bg-white text-red-600 border border-red-200 hover:bg-red-50 text-xs py-1 px-2.5"
                          onClick={() => handleAction(t.id, "cancel")}
                        >
                          ✕ Discard
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Manual Entry Modal */}
      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Record Manual Khata Entry">
        <form onSubmit={handleManualSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
              Select Customer *
            </label>
            <select
              className="input"
              required
              value={manualForm.customer_id}
              onChange={(e) => setManualForm({ ...manualForm, customer_id: e.target.value })}
            >
              <option value="">-- Choose customer --</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} {c.landmark ? `(${c.landmark})` : ""} - Due: {inr(c.balance)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
              Entry Type *
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setManualForm({ ...manualForm, type: "credit" })}
                className={`btn py-2 text-xs font-bold ${
                  manualForm.type === "credit"
                    ? "bg-red-600 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                Udhar (Credit)
              </button>
              <button
                type="button"
                onClick={() => setManualForm({ ...manualForm, type: "payment" })}
                className={`btn py-2 text-xs font-bold ${
                  manualForm.type === "payment"
                    ? "bg-emerald-600 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                Jama (Payment)
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
              Amount (₹) *
            </label>
            <input
              type="number"
              step="0.01"
              min="1"
              required
              className="input font-bold text-lg"
              placeholder="340.00"
              value={manualForm.amount}
              onChange={(e) => setManualForm({ ...manualForm, amount: e.target.value })}
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
              Note (Optional items / description)
            </label>
            <input
              className="input"
              placeholder="e.g. 5kg rice + oil"
              value={manualForm.note}
              onChange={(e) => setManualForm({ ...manualForm, note: e.target.value })}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setModalOpen(false)}
              className="btn bg-white border border-slate-300 text-slate-700"
            >
              Cancel
            </button>
            <button type="submit" className="btn bg-emerald-600 text-white hover:bg-emerald-700">
              Commit Entry
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}
