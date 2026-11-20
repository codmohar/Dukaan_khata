"use client";
import { useState } from "react";
import Link from "next/link";
import { api, Customer, inr, Txn, when, whatsAppReminderUrl } from "@/lib/api";
import { useLive } from "@/lib/supabase";
import { Badge, ErrorBanner, Modal, PageTitle } from "@/components/ui";

export default function CustomersPage() {
  const [list, setList] = useState<Customer[]>([]);
  const [shopName, setShopName] = useState("Kirana Store");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const [addForm, setAddForm] = useState({ name: "", phone: "", landmark: "" });

  // Inline quick WhatsApp registration state (only for customers without a phone)
  const [waEditId, setWaEditId] = useState<string | null>(null);
  const [waInput, setWaInput] = useState("");
  const [savingWa, setSavingWa] = useState(false);

  // Customer Edit modal state
  const [editingCust, setEditingCust] = useState<Customer | null>(null);
  const [editForm, setEditForm] = useState({ name: "", phone: "", landmark: "" });

  const [openId, setOpenId] = useState<string | null>(null);
  const [history, setHistory] = useState<Txn[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [err, setErr] = useState("");

  const loadCustomers = () => {
    api.shop().then((s) => { if (s?.name) setShopName(s.name); }).catch(() => {});
    api.customers(q)
      .then((data) => {
        setList(Array.isArray(data) ? data : []);
        setErr("");
      })
      .catch(() => setErr("Could not reach backend API. Check server connection."));
  };

  const handleSaveWhatsApp = async (customerId: string, e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const cleaned = waInput.trim();
    if (!cleaned) return;
    setSavingWa(true);
    try {
      await api.updateCustomer(customerId, { phone: cleaned });
      setWaEditId(null);
      setWaInput("");
      loadCustomers();
    } catch (ex) {
      setErr(String(ex));
    } finally {
      setSavingWa(false);
    }
  };

  useLive(loadCustomers, [q]);

  const toggleDetail = async (id: string) => {
    if (openId === id) {
      setOpenId(null);
      return;
    }
    setOpenId(id);
    setLoadingHistory(true);
    try {
      const txns = await api.txns({ customer_id: id, limit: "50" });
      setHistory(Array.isArray(txns) ? txns : []);
    } catch {
      setErr("Failed to load customer history");
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addForm.name.trim()) return;
    try {
      await api.addCustomer({
        name: addForm.name.trim(),
        phone: addForm.phone.trim() || undefined,
        landmark: addForm.landmark.trim() || undefined,
      });
      setAddForm({ name: "", phone: "", landmark: "" });
      setAdding(false);
      loadCustomers();
    } catch (e) {
      setErr(String(e));
    }
  };

  const startEdit = (c: Customer, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingCust(c);
    setEditForm({
      name: c.name,
      phone: c.phone || "",
      landmark: c.landmark || "",
    });
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCust) return;
    try {
      await api.updateCustomer(editingCust.id, {
        name: editForm.name.trim(),
        phone: editForm.phone.trim() || undefined,
        landmark: editForm.landmark.trim() || undefined,
      });
      setEditingCust(null);
      loadCustomers();
    } catch (e) {
      setErr(String(e));
    }
  };

  const handleDelete = async (c: Customer, e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (!confirm(`Are you sure you want to delete ${c.name} and all their khata history?`)) {
      return;
    }
    try {
      await api.deleteCustomer(c.id);
      if (openId === c.id) setOpenId(null);
      loadCustomers();
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <>
      <PageTitle title="Customer Ledger" sub={`${list.length} customers registered in shop`}>
        <button
          className="btn bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm flex items-center gap-1.5"
          onClick={() => setAdding(!adding)}
        >
          <span>{adding ? "✕ Close" : "+ Add Customer"}</span>
        </button>
      </PageTitle>

      <ErrorBanner msg={err} onClose={() => setErr("")} />

      {/* Add Customer Form */}
      {adding && (
        <form
          onSubmit={handleCreate}
          className="card mb-5 border-2 border-emerald-500/30 bg-emerald-50/40 p-4 shadow-sm"
        >
          <h3 className="font-bold text-slate-900 mb-3 text-sm">Register New Customer</h3>
          <div className="grid gap-3 sm:grid-cols-3">
            <input
              className="input bg-white"
              placeholder="Full Name * (e.g. Ramesh Gowda)"
              required
              value={addForm.name}
              onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
            />
            <input
              className="input bg-white"
              placeholder="Phone (e.g. 9845012345)"
              inputMode="tel"
              value={addForm.phone}
              onChange={(e) => setAddForm({ ...addForm, phone: e.target.value })}
            />
            <input
              className="input bg-white"
              placeholder="Landmark (e.g. Near Ganapathi Temple)"
              value={addForm.landmark}
              onChange={(e) => setAddForm({ ...addForm, landmark: e.target.value })}
            />
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <button type="button" onClick={() => setAdding(false)} className="btn bg-white border border-slate-300">
              Cancel
            </button>
            <button className="btn bg-emerald-600 text-white hover:bg-emerald-700">Save Customer</button>
          </div>
        </form>
      )}

      {/* Search Input */}
      <div className="relative mb-4">
        <input
          className="input pl-10 bg-white shadow-sm"
          placeholder="🔍 Search customers by name or landmark (e.g. 'Ramesh', 'temple')…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {q && (
          <button
            onClick={() => setQ("")}
            className="absolute right-3 top-2.5 text-xs text-slate-400 hover:text-slate-600"
          >
            Clear
          </button>
        )}
      </div>

      {/* Customer List */}
      <div className="space-y-2.5">
        {list.length === 0 ? (
          <div className="card py-12 text-center text-sm text-slate-400">
            No customers found matching &quot;{q}&quot;. Click &quot;+ Add Customer&quot; above to create one.
          </div>
        ) : (
          list.map((c) => {
            const bal = Number(c.balance);
            const isOpen = openId === c.id;
            const hasDue = bal > 0;
            const hasWhatsApp = Boolean(c.phone && c.phone.trim());
            const waUrl = whatsAppReminderUrl(c.phone, c.name, bal, shopName);

            return (
              <div
                key={c.id}
                className={`card !p-0 overflow-hidden transition-all duration-200 ${isOpen ? "ring-2 ring-emerald-500 shadow-md" : "hover:border-slate-300"
                  }`}
              >
                {/* Header row */}
                <div
                  onClick={() => toggleDetail(c.id)}
                  className="flex flex-wrap items-center justify-between p-4 cursor-pointer hover:bg-slate-50/70 gap-2"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 font-bold text-slate-700 text-base">
                      {c.name.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-bold text-slate-900 text-base">{c.name}</p>
                      </div>

                      {hasWhatsApp ? (
                        <p className="text-xs text-slate-500 mt-0.5">
                          {[c.landmark, c.phone].filter(Boolean).join(" · ")}
                        </p>
                      ) : (
                        <div className="mt-1 space-y-1.5" onClick={(e) => e.stopPropagation()}>
                          {c.landmark && (
                            <p className="text-xs text-slate-500">{c.landmark}</p>
                          )}
                          {waEditId === c.id ? (
                            <form
                              onSubmit={(e) => handleSaveWhatsApp(c.id, e)}
                              className="flex flex-wrap items-center gap-1.5"
                            >
                              <input
                                type="tel"
                                inputMode="tel"
                                autoFocus
                                required
                                placeholder="10-digit WhatsApp #"
                                value={waInput}
                                onChange={(e) => setWaInput(e.target.value)}
                                className="rounded-lg border border-emerald-400 bg-white px-2.5 py-1 text-xs font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500 w-40"
                              />
                              <button
                                type="submit"
                                disabled={savingWa}
                                className="rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
                              >
                                {savingWa ? "Saving…" : "Save"}
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setWaEditId(null);
                                  setWaInput("");
                                }}
                                className="rounded-lg bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-200"
                              >
                                Cancel
                              </button>
                            </form>
                          ) : (
                            <button
                              type="button"
                              onClick={() => {
                                setWaEditId(c.id);
                                setWaInput("");
                              }}
                              className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-300 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700 hover:bg-emerald-100 transition"
                            >
                              <span>📱</span>
                              <span>+ Add WhatsApp Number (for loan info)</span>
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {/* WhatsApp Reminder Button */}
                    {hasDue && c.phone && (
                      <a
                        href={waUrl}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="btn bg-emerald-50 text-emerald-700 border border-emerald-300 hover:bg-emerald-100 text-xs py-1 px-2.5 flex items-center gap-1"
                        title="Send WhatsApp payment reminder"
                      >
                        <span>💬</span>
                        <span className="hidden sm:inline">WhatsApp</span>
                      </a>
                    )}

                    <div className="text-right min-w-[5rem]">
                      <p
                        className={`text-lg font-black ${hasDue ? "text-red-600" : bal < 0 ? "text-emerald-600" : "text-slate-400"
                          }`}
                      >
                        {hasDue ? inr(bal) : bal < 0 ? `${inr(-bal)} adv` : "Clear"}
                      </p>
                      <p className="text-[10px] text-slate-400 font-medium">
                        {hasDue ? "Owes Shop" : bal < 0 ? "Advance Paid" : "No Due"}
                      </p>
                    </div>

                    <button
                      onClick={(e) => startEdit(c, e)}
                      className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
                      title="Edit Customer"
                    >
                      ✏️
                    </button>
                    <span className="text-slate-400 text-xs">{isOpen ? "▲" : "▼"}</span>
                  </div>
                </div>

                {/* Expanded Customer Ledger History */}
                {isOpen && (
                  <div className="border-t border-slate-100 bg-slate-50/60 p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                        Transaction History for {c.name}
                      </h4>
                      <span className="text-xs text-slate-400">{history.length} entries</span>
                    </div>

                    {loadingHistory ? (
                      <p className="py-4 text-center text-xs text-slate-400">Loading history…</p>
                    ) : history.length === 0 ? (
                      <p className="py-4 text-center text-xs text-slate-400">No transactions recorded yet.</p>
                    ) : (
                      <div className="divide-y divide-slate-200/60 rounded-xl bg-white border border-slate-200 overflow-hidden text-sm">
                        {history.map((t) => (
                          <div key={t.id} className="flex items-center justify-between p-3">
                            <div>
                              <div className="flex items-center gap-2">
                                <Badge status={t.status === "confirmed" ? t.type : t.status} />
                                <span className="font-semibold text-slate-800">
                                  {t.note || (t.type === "credit" ? "Credit Udhar" : "Cash Payment")}
                                </span>
                              </div>
                              <p className="text-[11px] text-slate-400 mt-0.5">{when(t.created_at)}</p>
                            </div>
                            <span
                              className={`font-bold ${t.type === "credit" ? "text-red-600" : "text-emerald-600"
                                }`}
                            >
                              {t.type === "credit" ? "+" : "−"}{inr(t.amount)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="mt-4 flex flex-wrap justify-between items-center gap-2">
                      <button
                        onClick={(e) => handleDelete(c, e)}
                        className="btn bg-white text-red-600 border border-red-200 hover:bg-red-50 text-xs px-3 py-1.5"
                      >
                        🗑️ Delete Customer
                      </button>
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/customers/${c.id}`}
                          className="btn bg-emerald-50 text-emerald-700 border border-emerald-300 hover:bg-emerald-100 text-xs px-3 py-1.5 font-bold flex items-center gap-1"
                        >
                          <span>👨‍👩‍👧‍👦</span>
                          <span>Household &amp; Dispute Timeline →</span>
                        </Link>
                        <button
                          onClick={() => toggleDetail(c.id)}
                          className="text-xs text-slate-500 hover:text-slate-800"
                        >
                          Close History
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Edit Customer Modal */}
      <Modal
        open={!!editingCust}
        onClose={() => setEditingCust(null)}
        title={`Edit Customer: ${editingCust?.name}`}
      >
        <form onSubmit={handleUpdate} className="space-y-4">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
              Customer Name *
            </label>
            <input
              className="input"
              required
              value={editForm.name}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
              Phone Number
            </label>
            <input
              className="input"
              value={editForm.phone}
              onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
              Landmark / Location
            </label>
            <input
              className="input"
              value={editForm.landmark}
              onChange={(e) => setEditForm({ ...editForm, landmark: e.target.value })}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setEditingCust(null)}
              className="btn bg-white border border-slate-300 text-slate-700"
            >
              Cancel
            </button>
            <button type="submit" className="btn bg-emerald-600 text-white hover:bg-emerald-700">
              Update Customer
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}
