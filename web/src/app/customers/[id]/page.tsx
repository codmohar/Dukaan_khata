"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  inr,
  when,
  Customer,
  HouseholdMember,
  DisputeTimeline,
  Txn,
  whatsAppReminderUrl,
} from "@/lib/api";
import { Badge, ErrorBanner, Modal, PageTitle } from "@/components/ui";

export default function CustomerDetailPage() {
  const params = useParams();
  const customerId = params?.id as string;

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [members, setMembers] = useState<HouseholdMember[]>([]);
  const [activeMemberId, setActiveMemberId] = useState<string | "ALL">("ALL");
  const [activeTab, setActiveTab] = useState<"ledger" | "timeline">("ledger");

  const [txns, setTxns] = useState<Txn[]>([]);
  const [timelineData, setTimelineData] = useState<DisputeTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  // Add Member Modal State
  const [addMemberOpen, setAddMemberOpen] = useState(false);
  const [memberForm, setMemberForm] = useState({
    member_name: "",
    relationship: "Son",
    is_authorized: true,
  });
  const [addingMember, setAddingMember] = useState(false);

  const loadData = async () => {
    if (!customerId) return;
    setLoading(true);
    try {
      const [c, mList, tList] = await Promise.all([
        api.customer(customerId),
        api.household(customerId).catch(() => []),
        api.txns({ customer_id: customerId, limit: "100" }),
      ]);
      setCustomer(c);
      setMembers(Array.isArray(mList) ? mList : []);
      setTxns(Array.isArray(tList) ? tList : []);
      setErr("");
    } catch (e: any) {
      setErr(e.message || "Failed to load customer details");
    } finally {
      setLoading(false);
    }
  };

  const loadTimeline = async (mId?: string) => {
    if (!customerId) return;
    try {
      const t = await api.timeline(customerId, mId === "ALL" ? undefined : mId);
      setTimelineData(t);
    } catch (e: any) {
      setErr(e.message || "Failed to load dispute timeline");
    }
  };

  useEffect(() => {
    loadData();
  }, [customerId]);

  useEffect(() => {
    if (activeTab === "timeline") {
      loadTimeline(activeMemberId === "ALL" ? undefined : activeMemberId);
    }
  }, [activeTab, activeMemberId]);

  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!memberForm.member_name.trim()) return;
    setAddingMember(true);
    try {
      await api.addHouseholdMember(customerId, {
        member_name: memberForm.member_name.trim(),
        relationship: memberForm.relationship,
        is_authorized: memberForm.is_authorized,
      });
      setAddMemberOpen(false);
      setMemberForm({ member_name: "", relationship: "Son", is_authorized: true });
      loadData();
    } catch (e: any) {
      setErr(e.message || "Failed to add household member");
    } finally {
      setAddingMember(false);
    }
  };

  if (loading && !customer) {
    return <div className="p-8 text-center text-slate-400">Loading household khata…</div>;
  }

  if (!customer) {
    return (
      <div className="p-8 text-center">
        <p className="text-red-600 font-bold">Customer not found</p>
        <Link href="/customers" className="mt-3 btn bg-slate-100 text-slate-700">
          ← Back to Customers
        </Link>
      </div>
    );
  }

  const bal = Number(customer.balance || customer.outstanding_balance || 0);
  const filteredTxns =
    activeMemberId === "ALL"
      ? txns
      : txns.filter((t) => t.member_id === activeMemberId);

  return (
    <>
      <div className="mb-4">
        <Link
          href="/customers"
          className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-500 hover:text-slate-800 transition"
        >
          <span>←</span> Back to All Customers
        </Link>
      </div>

      <PageTitle
        title={customer.name}
        sub={[customer.landmark, customer.phone].filter(Boolean).join(" · ") || "Household Account"}
      >
        <button
          onClick={() => setAddMemberOpen(true)}
          className="btn bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 text-xs font-bold px-3 py-1.5"
        >
          + Add Family Member
        </button>
      </PageTitle>

      <ErrorBanner msg={err} onClose={() => setErr("")} />

      {/* Household Balance Card */}
      <div className="card mb-6 flex flex-wrap items-center justify-between gap-4 border-2 border-slate-200">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Total Household Outstanding Balance
          </span>
          <p
            className={`text-3xl font-black mt-1 ${
              bal > 0 ? "text-red-600" : bal < 0 ? "text-emerald-600" : "text-slate-400"
            }`}
          >
            {bal > 0 ? inr(bal) : bal < 0 ? `${inr(-bal)} (Advance)` : "₹0.00 (All Clear)"}
          </p>
          <p className="text-xs text-slate-400 mt-0.5">
            Single shared balance across all family members in this household
          </p>
        </div>

        {bal > 0 && customer.phone && (
          <a
            href={whatsAppReminderUrl(customer.phone, customer.name, bal)}
            target="_blank"
            rel="noreferrer"
            className="btn bg-emerald-600 text-white hover:bg-emerald-700 text-xs font-bold px-4 py-2 flex items-center gap-1.5 shadow"
          >
            <span>💬</span>
            <span>Send WhatsApp Reminder</span>
          </a>
        )}
      </div>

      {/* Household Member Filter Pills */}
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <span className="text-xs font-bold text-slate-500 mr-1">Filter Member:</span>
        <button
          onClick={() => setActiveMemberId("ALL")}
          className={`rounded-full px-3.5 py-1 text-xs font-bold transition border ${
            activeMemberId === "ALL"
              ? "bg-emerald-600 text-white border-emerald-600 shadow-sm"
              : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
          }`}
        >
          All Household
        </button>
        {members.map((m) => (
          <button
            key={m.id}
            onClick={() => setActiveMemberId(m.id)}
            className={`rounded-full px-3.5 py-1 text-xs font-bold transition border flex items-center gap-1.5 ${
              activeMemberId === m.id
                ? "bg-emerald-600 text-white border-emerald-600 shadow-sm"
                : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
            }`}
          >
            <span>👤</span>
            <span>
              {m.member_name} {m.relationship ? `(${m.relationship})` : ""}
            </span>
            {!m.is_authorized && (
              <span className="text-[10px] text-amber-600 bg-amber-100 px-1.5 rounded-full font-bold">
                Limited
              </span>
            )}
          </button>
        ))}
        <button
          onClick={() => setAddMemberOpen(true)}
          className="rounded-full px-3 py-1 text-xs font-bold text-emerald-700 border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 transition"
        >
          + Add Member
        </button>
      </div>

      {/* Tabs: Ledger vs Dispute Timeline */}
      <div className="flex border-b border-slate-200 mb-4 gap-6">
        <button
          onClick={() => setActiveTab("ledger")}
          className={`pb-2.5 text-sm font-bold border-b-2 transition ${
            activeTab === "ledger"
              ? "border-emerald-600 text-emerald-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          📒 Ledger Transactions ({filteredTxns.length})
        </button>
        <button
          onClick={() => setActiveTab("timeline")}
          className={`pb-2.5 text-sm font-bold border-b-2 transition flex items-center gap-1.5 ${
            activeTab === "timeline"
              ? "border-emerald-600 text-emerald-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          <span>⚖️</span>
          <span>Smart Dispute Timeline</span>
          {timelineData?.balance_mismatch && (
            <span className="h-2 w-2 rounded-full bg-red-500 animate-ping" />
          )}
        </button>
      </div>

      {/* Tab 1: Ledger */}
      {activeTab === "ledger" && (
        <div className="card !p-0 overflow-hidden divide-y divide-slate-100">
          {filteredTxns.length === 0 ? (
            <p className="p-8 text-center text-xs text-slate-400">
              No ledger transactions recorded for this filter.
            </p>
          ) : (
            filteredTxns.map((t) => (
              <div key={t.id} className="p-3.5 flex items-center justify-between hover:bg-slate-50/70">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <Badge status={t.type} />
                    {t.member_name && (
                      <span className="text-xs font-bold bg-amber-100 text-amber-900 border border-amber-200 px-2 py-0.5 rounded-full">
                        👤 {t.member_name}
                      </span>
                    )}
                    <span className="text-xs font-semibold text-slate-800">
                      {t.note || t.item_note || (t.type === "credit" ? "Credit Udhar" : "Payment")}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    {when(t.created_at)}
                    {t.payment_mode ? ` · Mode: ${t.payment_mode.toUpperCase()}` : ""}
                  </p>
                </div>
                <div className="text-right">
                  <p
                    className={`text-base font-extrabold ${
                      t.type === "credit" ? "text-red-600" : "text-emerald-600"
                    }`}
                  >
                    {t.type === "credit" ? "+" : "−"}
                    {inr(t.amount)}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab 2: Smart Dispute Timeline */}
      {activeTab === "timeline" && (
        <div className="space-y-4">
          {timelineData?.balance_mismatch && (
            <div className="rounded-2xl border-2 border-red-500 bg-red-50 p-4 text-red-900 shadow-sm">
              <div className="flex items-center gap-2 font-black text-sm">
                <span className="text-lg">🚨</span>
                <span>Audit Alert: Balance Discrepancy Detected!</span>
              </div>
              <p className="text-xs mt-1">
                The stored customer balance ({inr(timelineData.current_balance)}) does not match the chronological
                cumulative ledger sum ({inr(timelineData.computed_final_balance)}). Review the highlighted evidence below.
              </p>
            </div>
          )}

          <div className="card !p-0 overflow-hidden divide-y divide-slate-100">
            {!timelineData || !Array.isArray(timelineData.timeline) || timelineData.timeline.length === 0 ? (
              <p className="p-8 text-center text-xs text-slate-400">
                No chronological dispute events found.
              </p>
            ) : (
              timelineData.timeline.map((ev, i) => (
                <div key={ev.transaction_id || i} className="p-4 hover:bg-slate-50/80 transition">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Badge status={ev.type} />
                      <span className="text-xs font-bold text-slate-700">
                        {when(ev.occurred_at)}
                      </span>
                      {ev.member_name && (
                        <span className="text-xs font-bold bg-amber-100 text-amber-900 border border-amber-200 px-2 py-0.5 rounded-full">
                          👤 {ev.member_name}
                        </span>
                      )}
                      {ev.payment_mode && (
                        <span className="text-xs text-slate-500 font-semibold">
                          {ev.payment_mode === "cash" ? "💵 Cash" : ev.payment_mode === "upi" ? "📱 UPI" : "💳"}
                        </span>
                      )}
                      {ev.rule_override && (
                        <span className="text-[10px] font-bold text-amber-800 bg-amber-100 border border-amber-300 px-1.5 py-0.5 rounded">
                          ⚠️ Policy Override
                        </span>
                      )}
                    </div>
                    <div className="text-right">
                      <span
                        className={`text-base font-black ${
                          ev.type === "credit" ? "text-red-600" : "text-emerald-600"
                        }`}
                      >
                        {ev.type === "credit" ? "+" : "−"}
                        {inr(ev.amount)}
                      </span>
                      <span className="text-xs font-bold text-slate-800 ml-3 bg-slate-100 px-2 py-0.5 rounded-lg">
                        Bal: {inr(ev.balance_after)}
                      </span>
                    </div>
                  </div>

                  {ev.item_note && (
                    <p className="mt-1 text-xs font-medium text-slate-700">
                      📦 Item: {ev.item_note}
                    </p>
                  )}

                  {/* Grounded Spoken Transcript Evidence */}
                  {ev.transcript_snippet && (
                    <div className="mt-2 rounded-xl bg-slate-100 border border-slate-200 p-2.5 text-xs text-slate-700 flex items-start gap-2">
                      <span className="text-sm">🗣️</span>
                      <div>
                        <span className="font-bold text-slate-600 text-[10px] uppercase tracking-wider block">
                          Recorded Voice Evidence:
                        </span>
                        <p className="italic text-slate-900 font-medium">
                          &quot;{ev.transcript_snippet}&quot;
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Add Household Member Modal */}
      <Modal open={addMemberOpen} onClose={() => setAddMemberOpen(false)} title="Add Family Member to Khata">
        <form onSubmit={handleAddMember} className="space-y-4 p-1">
          <p className="text-xs text-slate-500">
            Link a family member (son, spouse, parent, sibling) to {customer.name}&apos;s account.
            They share the household balance while every entry records who purchased it.
          </p>

          <div>
            <label className="text-xs font-bold text-slate-700 block mb-1">Member Name *</label>
            <input
              type="text"
              required
              autoFocus
              value={memberForm.member_name}
              onChange={(e) => setMemberForm({ ...memberForm, member_name: e.target.value })}
              placeholder="e.g. Arjun, Sunita, Ravi"
              className="w-full rounded-xl border border-slate-300 p-2.5 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <div>
            <label className="text-xs font-bold text-slate-700 block mb-1">Relationship</label>
            <select
              value={memberForm.relationship}
              onChange={(e) => setMemberForm({ ...memberForm, relationship: e.target.value })}
              className="w-full rounded-xl border border-slate-300 p-2.5 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
            >
              <option value="Son">Son (Maga)</option>
              <option value="Daughter">Daughter (MagaLu)</option>
              <option value="Wife">Wife (Hendathi)</option>
              <option value="Husband">Husband (Ganda)</option>
              <option value="Brother">Brother (Anna/Tamma)</option>
              <option value="Sister">Sister (Akka/Tangi)</option>
              <option value="Father">Father (Appa)</option>
              <option value="Mother">Mother (Amma)</option>
              <option value="Other">Other / Relative</option>
            </select>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <input
              type="checkbox"
              id="is_auth"
              checked={memberForm.is_authorized}
              onChange={(e) => setMemberForm({ ...memberForm, is_authorized: e.target.checked })}
              className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
            />
            <label htmlFor="is_auth" className="text-xs font-semibold text-slate-700 cursor-pointer">
              Authorized to take udhar credit without special approval
            </label>
          </div>

          <div className="flex justify-end gap-2 pt-3">
            <button
              type="button"
              onClick={() => setAddMemberOpen(false)}
              className="btn bg-slate-100 text-slate-600 px-4 py-2 text-xs font-bold hover:bg-slate-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={addingMember}
              className="btn bg-emerald-600 text-white px-5 py-2 text-xs font-bold hover:bg-emerald-700"
            >
              {addingMember ? "Saving..." : "Save Member"}
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}

