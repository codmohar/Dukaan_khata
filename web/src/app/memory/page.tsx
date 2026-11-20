"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  inr,
  when,
  PromiseItem,
  ShopRule,
  DailyReconciliationItem,
} from "@/lib/api";
import { Badge, ErrorBanner, Modal, PageTitle } from "@/components/ui";

export default function MemoryAndRulesPage() {
  const [activeTab, setActiveTab] = useState<"promises" | "rules" | "reconciliation">("promises");

  // Search Memory State
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[] | null>(null);
  const [searching, setSearching] = useState(false);

  // Tab 1: Promises State
  const [promises, setPromises] = useState<PromiseItem[]>([]);
  const [promiseFilter, setPromiseFilter] = useState<string>("ALL");
  const [reschedulePromise, setReschedulePromise] = useState<PromiseItem | null>(null);
  const [newDateInput, setNewDateInput] = useState("");

  // Tab 2: Rules State
  const [rules, setRules] = useState<ShopRule[]>([]);
  const [addRuleOpen, setAddRuleOpen] = useState(false);
  const [ruleForm, setRuleForm] = useState({
    rule_category: "NEW_CUSTOMER_CAP",
    rule_text: "",
    max_amount: "1000",
  });
  const [savingRule, setSavingRule] = useState(false);

  // Tab 3: Reconciliations State
  const [reconciliations, setReconciliations] = useState<DailyReconciliationItem[]>([]);
  const [expandedRecId, setExpandedRecId] = useState<string | null>(null);
  const [resolveRec, setResolveRec] = useState<DailyReconciliationItem | null>(null);
  const [resolveNote, setResolveNote] = useState("");
  const [resolving, setResolving] = useState(false);

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const loadData = async () => {
    setLoading(true);
    try {
      const [pList, rList, recList] = await Promise.all([
        api.promises().catch(() => []),
        api.rules().catch(() => []),
        api.reconciliations().catch(() => []),
      ]);
      setPromises(Array.isArray(pList) ? pList : []);
      setRules(Array.isArray(rList) ? rList : []);
      setReconciliations(Array.isArray(recList) ? recList : []);
      setErr("");
    } catch (e: any) {
      setErr(e.message || "Failed to load memory data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    try {
      const res = await api.memorySearch(q);
      setSearchResults(res.results || []);
    } catch (e: any) {
      setErr(e.message || "Memory recall search failed");
    } finally {
      setSearching(false);
    }
  };

  // Promise Actions
  const handleReschedule = async () => {
    if (!reschedulePromise || !newDateInput) return;
    try {
      await api.updatePromise(reschedulePromise.id, { expected_date: newDateInput });
      setReschedulePromise(null);
      setNewDateInput("");
      loadData();
    } catch (e: any) {
      setErr(e.message || "Failed to reschedule promise");
    }
  };

  const handleCancelPromise = async (id: string) => {
    try {
      await api.updatePromise(id, { status: "CANCELLED" });
      loadData();
    } catch (e: any) {
      setErr(e.message || "Failed to cancel promise");
    }
  };

  // Rule Actions
  const handleToggleRule = async (r: ShopRule) => {
    try {
      await api.toggleRule(r.id, !r.is_active);
      setRules((prev) =>
        prev.map((item) => (item.id === r.id ? { ...item, is_active: !item.is_active } : item))
      );
    } catch (e: any) {
      setErr(e.message || "Failed to toggle rule");
    }
  };

  const handleDeleteRule = async (id: string) => {
    try {
      await api.deleteRule(id);
      setRules((prev) => prev.filter((r) => r.id !== id));
    } catch (e: any) {
      setErr(e.message || "Failed to delete rule");
    }
  };

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ruleForm.rule_text.trim()) return;
    setSavingRule(true);
    try {
      let condition: any = {};
      const amt = Number(ruleForm.max_amount) || 1000;
      if (ruleForm.rule_category === "NEW_CUSTOMER_CAP") {
        condition = { max_amount: amt };
      } else if (ruleForm.rule_category === "BALANCE_CAP") {
        condition = { max_balance: amt };
      } else if (ruleForm.rule_category === "TIME_CUTOFF") {
        condition = { after: "20:00", tz: "Asia/Kolkata" };
      } else {
        condition = { max_amount: amt };
      }

      await api.addRule({
        rule_category: ruleForm.rule_category,
        rule_text: ruleForm.rule_text.trim(),
        structured_condition: condition,
      });
      setAddRuleOpen(false);
      setRuleForm({ rule_category: "NEW_CUSTOMER_CAP", rule_text: "", max_amount: "1000" });
      loadData();
    } catch (e: any) {
      setErr(e.message || "Failed to create rule");
    } finally {
      setSavingRule(false);
    }
  };

  // Reconciliation Actions
  const handleResolve = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resolveRec || !resolveNote.trim()) return;
    setResolving(true);
    try {
      await api.resolveReconciliation(resolveRec.id, resolveNote.trim());
      setResolveRec(null);
      setResolveNote("");
      loadData();
    } catch (e: any) {
      setErr(e.message || "Failed to resolve reconciliation");
    } finally {
      setResolving(false);
    }
  };

  const filteredPromises =
    promiseFilter === "ALL"
      ? promises
      : promises.filter((p) => p.status.toUpperCase() === promiseFilter.toUpperCase());

  return (
    <>
      <PageTitle
        title="Memory & Rules"
        sub="Shopkeeper AI memory, spoken dukaan credit policies, and daily balance audits"
      >
        <Link
          href="/voice"
          className="btn bg-emerald-600 text-white hover:bg-emerald-700 text-xs font-bold px-3 py-1.5 flex items-center gap-1.5"
        >
          <span>🎙️</span>
          <span>Add by Voice</span>
        </Link>
      </PageTitle>

      <ErrorBanner msg={err} onClose={() => setErr("")} />

      {/* Ask Memory Universal Search Box */}
      <div className="card mb-6 border border-slate-200">
        <form onSubmit={handleSearch} className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[240px]">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Ask memory: 'Ramesh ne kab promise kiya?', 'Who owes rice?', 'What is the credit rule?'"
              className="w-full rounded-xl border border-slate-300 py-2.5 pl-9 pr-3 text-sm font-semibold text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <span className="absolute left-3 top-3 text-slate-400">🔍</span>
          </div>
          <button
            type="submit"
            disabled={searching}
            className="btn bg-slate-900 text-white px-4 py-2.5 text-xs font-bold hover:bg-slate-800"
          >
            {searching ? "Searching…" : "Recall"}
          </button>
          {searchResults !== null && (
            <button
              type="button"
              onClick={() => {
                setSearchResults(null);
                setSearchQuery("");
              }}
              className="btn bg-slate-100 text-slate-600 px-3 py-2.5 text-xs font-bold hover:bg-slate-200"
            >
              Clear
            </button>
          )}
        </form>

        {/* Search Results Display */}
        {searchResults !== null && (
          <div className="mt-4 pt-3 border-t border-slate-100">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
              Memory Search Results ({searchResults.length})
            </h4>
            {searchResults.length === 0 ? (
              <p className="text-xs text-slate-400 py-2">
                No matching promises, transactions, or rules found.
              </p>
            ) : (
              <div className="space-y-2">
                {searchResults.map((r, idx) => (
                  <div
                    key={idx}
                    className="p-3 rounded-xl border border-slate-200 bg-slate-50 flex items-start justify-between gap-3 text-xs"
                  >
                    <div>
                      <div className="flex items-center gap-1.5 mb-1">
                        <span
                          className={`px-2 py-0.5 rounded-full font-bold uppercase text-[10px] ${
                            r.source === "promise"
                              ? "bg-blue-100 text-blue-800"
                              : r.source === "transaction"
                              ? "bg-emerald-100 text-emerald-800"
                              : "bg-purple-100 text-purple-800"
                          }`}
                        >
                          {r.source}
                        </span>
                        <span className="font-extrabold text-slate-900">
                          {r.entity_name || r.customer_name || r.rule_category}
                        </span>
                      </div>
                      <p className="text-slate-700 font-medium">
                        {r.description || r.item_note || r.rule_text}
                      </p>
                      {r.transcript_snippet && (
                        <p className="text-slate-500 italic mt-0.5">&quot;{r.transcript_snippet}&quot;</p>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      {r.promised_amount ? (
                        <span className="font-bold text-blue-700 text-sm">{inr(r.promised_amount)}</span>
                      ) : r.amount ? (
                        <span className="font-bold text-slate-900 text-sm">{inr(r.amount)}</span>
                      ) : null}
                      {r.expected_date && (
                        <p className="text-[10px] text-slate-400 mt-0.5">Due: {r.expected_date}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 3 Main Tabs */}
      <div className="flex border-b border-slate-200 mb-5 gap-6">
        <button
          onClick={() => setActiveTab("promises")}
          className={`pb-2.5 text-sm font-bold border-b-2 transition flex items-center gap-1.5 ${
            activeTab === "promises"
              ? "border-emerald-600 text-emerald-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          <span>🤝</span>
          <span>Promise Memory ({promises.length})</span>
        </button>

        <button
          onClick={() => setActiveTab("rules")}
          className={`pb-2.5 text-sm font-bold border-b-2 transition flex items-center gap-1.5 ${
            activeTab === "rules"
              ? "border-emerald-600 text-emerald-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          <span>📜</span>
          <span>Dukaan Rules ({rules.length})</span>
        </button>

        <button
          onClick={() => setActiveTab("reconciliation")}
          className={`pb-2.5 text-sm font-bold border-b-2 transition flex items-center gap-1.5 ${
            activeTab === "reconciliation"
              ? "border-emerald-600 text-emerald-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          <span>⚖️</span>
          <span>Daily Reconciliations ({reconciliations.length})</span>
        </button>
      </div>

      {/* TAB 1: PROMISE MEMORY */}
      {activeTab === "promises" && (
        <div className="space-y-4">
          {/* Status Filter Pills */}
          <div className="flex items-center gap-2">
            {["ALL", "PENDING", "OVERDUE", "FULFILLED", "CANCELLED"].map((st) => (
              <button
                key={st}
                onClick={() => setPromiseFilter(st)}
                className={`rounded-full px-3 py-1 text-xs font-bold transition border ${
                  promiseFilter === st
                    ? "bg-slate-900 text-white border-slate-900"
                    : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          <div className="card !p-0 overflow-hidden divide-y divide-slate-100">
            {filteredPromises.length === 0 ? (
              <p className="p-8 text-center text-xs text-slate-400">
                No promises found matching &quot;{promiseFilter}&quot;.
              </p>
            ) : (
              filteredPromises.map((p) => {
                const isPending = p.status === "PENDING";
                const isOverdue = p.status === "OVERDUE";
                const isFulfilled = p.status === "FULFILLED";

                return (
                  <div key={p.id} className="p-4 flex flex-wrap items-center justify-between gap-3 hover:bg-slate-50/70">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-base">
                          {p.promise_type === "PAYMENT_PROMISE"
                            ? "💵"
                            : p.promise_type === "GOODS_RESERVATION"
                            ? "📦"
                            : "🚚"}
                        </span>
                        <span className="font-extrabold text-slate-900 text-sm">{p.entity_name}</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase ${
                            isPending
                              ? "bg-blue-100 text-blue-800"
                              : isOverdue
                              ? "bg-red-100 text-red-800 animate-pulse"
                              : isFulfilled
                              ? "bg-emerald-100 text-emerald-800"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {p.status}
                        </span>
                      </div>
                      <p className="text-xs text-slate-600 font-medium">{p.description}</p>
                      <p className="text-[11px] text-slate-400">
                        Expected: <b>{p.expected_date}</b>
                        {p.fulfilled_at ? ` · Fulfilled on ${when(p.fulfilled_at)}` : ""}
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      {p.promised_amount && (
                        <span className="text-lg font-black text-slate-900">{inr(p.promised_amount)}</span>
                      )}

                      {(isPending || isOverdue) && (
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => {
                              setReschedulePromise(p);
                              setNewDateInput(p.expected_date);
                            }}
                            className="btn bg-white border border-slate-300 text-slate-700 text-xs px-2.5 py-1 hover:bg-slate-50 font-bold"
                          >
                            Reschedule
                          </button>
                          <button
                            onClick={() => handleCancelPromise(p.id)}
                            className="btn bg-white border border-red-200 text-red-600 text-xs px-2.5 py-1 hover:bg-red-50 font-bold"
                          >
                            Cancel
                          </button>
                          <Link
                            href="/voice"
                            className="btn bg-emerald-600 text-white text-xs px-2.5 py-1 hover:bg-emerald-700 font-bold"
                            title="Speak payment to auto-fulfil this promise atomically"
                          >
                            ✓ Pay
                          </Link>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* TAB 2: DUKAAN RULES */}
      {activeTab === "rules" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-500">
              Active shop policies evaluated deterministically whenever a draft credit transaction is created.
            </p>
            <button
              onClick={() => setAddRuleOpen(true)}
              className="btn bg-slate-900 text-white hover:bg-slate-800 text-xs font-bold px-3 py-1.5"
            >
              + Create Rule Policy
            </button>
          </div>

          <div className="card !p-0 overflow-hidden divide-y divide-slate-100">
            {rules.length === 0 ? (
              <p className="p-8 text-center text-xs text-slate-400">
                No rules active. Speak any policy in Voice Khata (e.g. &quot;Naye customer ko 1000 se zyada udhar mat do&quot;)
                or click &quot;+ Create Rule Policy&quot;.
              </p>
            ) : (
              rules.map((r) => (
                <div key={r.id} className="p-4 flex items-center justify-between gap-3 hover:bg-slate-50/70">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-slate-900 text-sm">&quot;{r.rule_text}&quot;</span>
                      <span className="rounded-md bg-purple-100 text-purple-800 border border-purple-200 px-2 py-0.5 text-[10px] font-bold">
                        {r.rule_category}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Condition: {JSON.stringify(r.structured_condition)}
                    </p>
                  </div>

                  <div className="flex items-center gap-3">
                    {/* Active Toggle Switch */}
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={r.is_active}
                        onChange={() => handleToggleRule(r)}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-600"></div>
                      <span className="ml-2 text-xs font-bold text-slate-600">
                        {r.is_active ? "Active" : "Paused"}
                      </span>
                    </label>

                    <button
                      onClick={() => handleDeleteRule(r.id)}
                      className="text-slate-400 hover:text-red-600 p-1 text-sm transition"
                      title="Delete Rule"
                    >
                      🗑️
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* TAB 3: DAILY RECONCILIATIONS */}
      {activeTab === "reconciliation" && (
        <div className="space-y-4">
          <p className="text-xs text-slate-500">
            End-of-day audit logs comparing physical drawer cash and UPI statements with recorded payments.
          </p>

          <div className="card !p-0 overflow-hidden">
            {reconciliations.length === 0 ? (
              <p className="p-8 text-center text-xs text-slate-400">
                No reconciliations recorded yet. Run &quot;Start Evening Reconciliation&quot; on Dashboard or say &quot;Khata check karo&quot; in Voice.
              </p>
            ) : (
              <div className="divide-y divide-slate-100">
                {reconciliations.map((rec) => {
                  const isExpanded = expandedRecId === rec.id;
                  const isMatched = rec.status === "MATCHED";

                  return (
                    <div key={rec.id} className="transition">
                      <div
                        onClick={() => setExpandedRecId(isExpanded ? null : rec.id)}
                        className="p-4 flex flex-wrap items-center justify-between gap-3 cursor-pointer hover:bg-slate-50/70"
                      >
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2">
                            <span className="font-extrabold text-slate-900 text-sm">
                              📅 {rec.reconciliation_date}
                            </span>
                            <span
                              className={`rounded-full px-2.5 py-0.5 text-xs font-extrabold uppercase ${
                                isMatched
                                  ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                                  : rec.status === "RESOLVED"
                                  ? "bg-blue-100 text-blue-800 border border-blue-300"
                                  : "bg-amber-100 text-amber-800 border border-amber-300"
                              }`}
                            >
                              {rec.status}
                            </span>
                          </div>
                          <p className="text-xs text-slate-500">
                            Cash Recorded: {inr(rec.recorded_cash)} vs Actual: {inr(rec.actual_cash)} · UPI Recorded: {inr(rec.recorded_upi)} vs Actual: {inr(rec.actual_upi)}
                          </p>
                        </div>

                        <div className="flex items-center gap-3">
                          <div className="text-right">
                            <p
                              className={`text-xs font-bold ${
                                Number(rec.cash_difference) === 0 ? "text-slate-400" : "text-amber-600"
                              }`}
                            >
                              Cash Diff: {inr(rec.cash_difference)}
                            </p>
                            <p
                              className={`text-xs font-bold ${
                                Number(rec.upi_difference) === 0 ? "text-slate-400" : "text-amber-600"
                              }`}
                            >
                              UPI Diff: {inr(rec.upi_difference)}
                            </p>
                          </div>
                          <span className="text-slate-400 text-xs">{isExpanded ? "▲" : "▼"}</span>
                        </div>
                      </div>

                      {/* Expanded Findings Detail */}
                      {isExpanded && (
                        <div className="bg-slate-50/80 p-4 border-t border-slate-100 space-y-3">
                          {rec.audit_notes && (
                            <p className="text-xs text-slate-600 font-medium bg-white p-2.5 rounded-lg border">
                              📝 Resolution / Audit Note: {rec.audit_notes}
                            </p>
                          )}

                          <h5 className="text-xs font-bold uppercase text-slate-500">
                            Diagnostic Findings ({rec.findings?.length || 0})
                          </h5>
                          {!rec.findings || rec.findings.length === 0 ? (
                            <p className="text-xs text-emerald-700 font-medium">
                              ✓ 0 discrepancies found. Clean ledger match.
                            </p>
                          ) : (
                            <div className="space-y-1.5">
                              {rec.findings.map((f, idx) => (
                                <div
                                  key={idx}
                                  className="p-2.5 rounded-lg bg-white border border-amber-200 text-xs text-slate-800 flex items-start gap-2"
                                >
                                  <span className="text-amber-600 font-bold">⚠️</span>
                                  <div>
                                    <span className="font-bold text-amber-900 mr-1">
                                      [{f.kind}]
                                    </span>
                                    <span>{f.message}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}

                          {rec.status === "NEEDS_INVESTIGATION" && (
                            <div className="pt-2 flex justify-end">
                              <button
                                onClick={() => setResolveRec(rec)}
                                className="btn bg-blue-600 text-white hover:bg-blue-700 text-xs font-bold px-3 py-1.5"
                              >
                                ✓ Mark as Resolved
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Reschedule Promise Modal */}
      <Modal open={Boolean(reschedulePromise)} onClose={() => setReschedulePromise(null)} title="Reschedule Promise Date">
        <div className="space-y-3 p-1">
          <p className="text-xs text-slate-500">
            Update expected date for {reschedulePromise?.entity_name}&apos;s promise.
          </p>
          <div>
            <label className="text-xs font-bold text-slate-700 block mb-1">New Expected Date</label>
            <input
              type="date"
              value={newDateInput}
              onChange={(e) => setNewDateInput(e.target.value)}
              className="w-full rounded-xl border border-slate-300 p-2.5 text-sm font-semibold"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              onClick={() => setReschedulePromise(null)}
              className="btn bg-slate-100 text-slate-600 px-3 py-1.5 text-xs font-bold hover:bg-slate-200"
            >
              Cancel
            </button>
            <button
              onClick={handleReschedule}
              className="btn bg-emerald-600 text-white px-4 py-1.5 text-xs font-bold hover:bg-emerald-700"
            >
              Save New Date
            </button>
          </div>
        </div>
      </Modal>

      {/* Create Rule Modal */}
      <Modal open={addRuleOpen} onClose={() => setAddRuleOpen(false)} title="Create Shop Credit Policy Rule">
        <form onSubmit={handleCreateRule} className="space-y-3 p-1">
          <div>
            <label className="text-xs font-bold text-slate-700 block mb-1">Rule Category</label>
            <select
              value={ruleForm.rule_category}
              onChange={(e) => setRuleForm({ ...ruleForm, rule_category: e.target.value })}
              className="w-full rounded-xl border border-slate-300 p-2.5 text-xs font-semibold bg-white"
            >
              <option value="NEW_CUSTOMER_CAP">NEW_CUSTOMER_CAP (Max credit for first-time customers)</option>
              <option value="BALANCE_CAP">BALANCE_CAP (Max outstanding balance cap per customer)</option>
              <option value="TIME_CUTOFF">TIME_CUTOFF (Disallow credit after hours, e.g. 8 PM)</option>
              <option value="FREQUENCY_CAP">FREQUENCY_CAP (Max credit transactions per day)</option>
              <option value="DISALLOW_MEMBER_CREDIT">DISALLOW_MEMBER_CREDIT (Block unauthorized members)</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-bold text-slate-700 block mb-1">Max Amount Limit (₹)</label>
            <input
              type="number"
              value={ruleForm.max_amount}
              onChange={(e) => setRuleForm({ ...ruleForm, max_amount: e.target.value })}
              className="w-full rounded-xl border border-slate-300 p-2.5 text-sm font-semibold"
            />
          </div>

          <div>
            <label className="text-xs font-bold text-slate-700 block mb-1">Shopkeeper Voice Rule Text *</label>
            <input
              type="text"
              required
              value={ruleForm.rule_text}
              onChange={(e) => setRuleForm({ ...ruleForm, rule_text: e.target.value })}
              placeholder="e.g. Naye customer ko 1,000 se zyada udhar mat do"
              className="w-full rounded-xl border border-slate-300 p-2.5 text-sm font-semibold"
            />
          </div>

          <div className="flex justify-end gap-2 pt-3">
            <button
              type="button"
              onClick={() => setAddRuleOpen(false)}
              className="btn bg-slate-100 text-slate-600 px-3 py-1.5 text-xs font-bold hover:bg-slate-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={savingRule}
              className="btn bg-slate-900 text-white px-4 py-1.5 text-xs font-bold hover:bg-slate-800"
            >
              {savingRule ? "Saving…" : "Save Policy"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Resolve Reconciliation Modal */}
      <Modal open={Boolean(resolveRec)} onClose={() => setResolveRec(null)} title="Mark Reconciliation as Resolved">
        <form onSubmit={handleResolve} className="space-y-3 p-1">
          <p className="text-xs text-slate-500">
            Provide an audit note explaining the discrepancy (e.g. &quot;Customer Ramesh cash paid late at 10 PM&quot;).
          </p>
          <div>
            <label className="text-xs font-bold text-slate-700 block mb-1">Resolution Note *</label>
            <textarea
              required
              rows={3}
              value={resolveNote}
              onChange={(e) => setResolveNote(e.target.value)}
              placeholder="Explain how the discrepancy was verified or settled..."
              className="w-full rounded-xl border border-slate-300 p-2.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setResolveRec(null)}
              className="btn bg-slate-100 text-slate-600 px-3 py-1.5 text-xs font-bold hover:bg-slate-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={resolving}
              className="btn bg-blue-600 text-white px-4 py-1.5 text-xs font-bold hover:bg-blue-700"
            >
              {resolving ? "Resolving…" : "Save Resolution"}
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}

