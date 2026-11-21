"use client";
import { useEffect, useRef, useState } from "react";
import { api, inr, Shop, whatsAppReminderUrl } from "@/lib/api";
import { useVoice } from "@/lib/useVoice";
import { LANGS, PageTitle } from "@/components/ui";

const LABEL: Record<string, string> = {
  connecting: "Connecting to DukaanAI…",
  offline: "Server offline. Retrying…",
  idle: "Microphone stopped. Click to start Hands-Free Mode",
  monitoring: "👂 Hands-Free Active: Just speak anytime or say “Hi Khata”",
  listening: "🎙️ Recording Voice… (auto-submits when you pause)",
  thinking: "⚡ Processing voice & ledger…",
  speaking: "🔊 Speaking reply…",
};

export default function VoicePage() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [lang, setLang] = useState("hi-IN");
  const [typedText, setTypedText] = useState("");
  const [draftWaOpen, setDraftWaOpen] = useState(false);
  const [draftWaNum, setDraftWaNum] = useState("");
  const [draftWaSaved, setDraftWaSaved] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.shop().then(setShop).catch(() => {});
    const saved = localStorage.getItem("dukaan_lang") ?? "hi-IN";
    setLang(saved);
  }, []);

  const voice = useVoice(lang);

  useEffect(() => {
    setDraftWaOpen(false);
    setDraftWaNum("");
    setDraftWaSaved(null);
  }, [voice.draft?.draft_id]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [voice.msgs, voice.draft]);

  // Spacebar hands-free hotkey
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.code === "Space" && (e.target as HTMLElement)?.tagName !== "INPUT") {
        e.preventDefault();
        if (voice.status === "listening") {
          voice.stop();
        } else if (voice.status === "idle") {
          voice.start();
        }
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [voice]);

  const changeLang = (code: string) => {
    setLang(code);
    localStorage.setItem("dukaan_lang", code);
  };

  const isListening = voice.status === "listening";
  const isBusy =
    voice.status === "thinking" ||
    voice.status === "speaking" ||
    voice.status === "connecting" ||
    voice.status === "offline";

  const currentLangObj = LANGS.find((l) => l.code === lang) || LANGS[0];

  const quickChips = [
    { label: "Today's Summary", text: "Aaj kitna udhar aur UPI collection hua?" },
    { label: "Top Debtors", text: "Sabse zyada baaki kiska hai?" },
    { label: "Undo Last Entry", text: "Last entry delete maadi" },
    { label: "Confirm Entry", text: "Haan, theek hai confirm karo" },
  ];

  return (
    <>
      <PageTitle
        title="Voice Khata"
        sub={
          shop?.name
            ? `${shop.name} • Say “Hi Khata” or tap the speaker/mic to speak any command in any language`
            : "Say “Hi Khata” or tap the speaker/mic to speak any command in any language"
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          {/* Hands-Free VAD Toggle */}
          <button
            onClick={() => voice.setHandsFree(!voice.handsFree)}
            className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition border ${
              voice.handsFree
                ? "bg-emerald-50 text-emerald-700 border-emerald-300 shadow-sm"
                : "bg-slate-50 text-slate-500 border-slate-200"
            }`}
            title="When ON, simply speak anytime; when you pause, it auto-submits!"
          >
            <span
              className={`h-2 w-2 rounded-full ${
                voice.handsFree && voice.micActive ? "bg-emerald-500 animate-ping" : "bg-slate-400"
              }`}
            />
            <span>Hands-Free VAD: {voice.handsFree ? "ACTIVE" : "OFF"}</span>
          </button>

          {/* Wake Word "Hi Khata" toggle */}
          <button
            onClick={() => voice.setWakeWordActive(!voice.wakeWordActive)}
            className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition border ${
              voice.wakeWordActive
                ? "bg-purple-50 text-purple-700 border-purple-300 shadow-sm"
                : "bg-slate-50 text-slate-500 border-slate-200"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                voice.wakeWordActive ? "bg-purple-500 animate-pulse" : "bg-slate-400"
              }`}
            />
            <span>Wake Word “Hi Khata”: {voice.wakeWordActive ? "ON" : "OFF"}</span>
          </button>

          {/* Language selector */}
          <div className="flex flex-wrap gap-1 rounded-xl bg-white p-1 shadow-sm border border-slate-200">
            {LANGS.map((l) => (
              <button
                key={l.code}
                onClick={() => changeLang(l.code)}
                className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                  lang === l.code
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {l.label.split(" ")[0]}
              </button>
            ))}
          </div>
        </div>
      </PageTitle>

      {/* Mic Activation Prompt Banner if mic not active yet */}
      {!voice.micActive && (
        <div className="mb-4 rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-center shadow-sm">
          <p className="font-bold text-emerald-950 text-sm">
            🎙️ Hands-Free Zero-Click Voice is Ready
          </p>
          <p className="text-xs text-emerald-800 mt-1">
            Click once below to allow microphone listening. After this single tap, you never need to click any button again — just speak naturally or say “Hi Khata”!
          </p>
          <button
            onClick={voice.startContinuousVAD}
            className="mt-3 inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2 text-xs font-bold text-white shadow hover:bg-emerald-700 transition active:scale-95"
          >
            ⚡ Enable Hands-Free Continuous Intake
          </button>
        </div>
      )}

      {/* Wake Word Trigger Banner */}
      {voice.wakeDetected && (
        <div className="mb-4 rounded-xl border border-emerald-400 bg-emerald-500/10 p-3 text-center text-sm font-bold text-emerald-700 animate-bounce">
          🎯 &quot;Hi Khata&quot; heard! Listening to your voice message now…
        </div>
      )}

      {/* Main Speaker / Microphone Interaction Station */}
      <div className="card mb-6 flex flex-col items-center justify-center py-8 text-center bg-gradient-to-b from-white to-slate-50 border-slate-200 shadow-sm">
        <div className="relative">
          {isListening && (
            <div className="absolute inset-0 -m-6 rounded-full bg-red-400/30 animate-ping" />
          )}
          {isListening && (
            <div className="absolute inset-0 -m-3 rounded-full bg-red-500/40 animate-pulse" />
          )}
          {voice.status === "monitoring" && (
            <div className="absolute inset-0 -m-3 rounded-full bg-emerald-400/20 animate-pulse" />
          )}
          <button
            onClick={isListening ? voice.stop : voice.start}
            disabled={isBusy}
            aria-label="Speaker / Microphone"
            className={`relative flex h-32 w-32 items-center justify-center rounded-full text-5xl text-white shadow-xl transition-all duration-300 transform active:scale-95 disabled:opacity-50 ${
              isListening
                ? "bg-red-500 hover:bg-red-600 scale-105"
                : voice.status === "monitoring"
                ? "bg-emerald-600 hover:bg-emerald-700 shadow-emerald-700/30 ring-4 ring-emerald-300"
                : "bg-emerald-600 hover:bg-emerald-700 shadow-emerald-700/30 hover:scale-105"
            }`}
          >
            {isListening ? "⏹" : voice.status === "monitoring" ? "👂" : "🎙️"}
          </button>
        </div>

        {/* Live Audio Level Meter Bar */}
        {voice.micActive && (
          <div className="mt-4 flex flex-col items-center gap-1.5 w-full max-w-xs">
            <div className="flex items-center justify-between w-full text-[11px] font-semibold text-slate-500">
              <span>Mic Audio Level</span>
              <span className={voice.audioLevel > 15 ? "text-emerald-600 font-bold" : "text-slate-400"}>
                {voice.audioLevel > 15 ? "Speaking Detected" : "Quiet / Ambient"}
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-slate-200 overflow-hidden">
              <div
                className={`h-full transition-all duration-75 rounded-full ${
                  voice.audioLevel > 15 ? "bg-emerald-500" : "bg-slate-400"
                }`}
                style={{ width: `${Math.min(100, voice.audioLevel * 1.5)}%` }}
              />
            </div>
          </div>
        )}

        <p className="mt-4 text-lg font-bold text-slate-800">{LABEL[voice.status]}</p>

        {voice.interimText && (
          <div className="mt-2.5 max-w-md w-full px-4 py-2 rounded-xl bg-emerald-50 border border-emerald-300 text-emerald-900 font-semibold text-sm shadow-sm animate-pulse text-center">
            🗣️ &ldquo;{voice.interimText}&rdquo;
          </div>
        )}

        <p className="text-xs text-slate-500 mt-1 max-w-md">
          {isListening
            ? "Speak naturally. Release button or pause speaking to submit."
            : "Click the speaker/mic sign or say “Hi Khata” to give your message in any language."}
        </p>

        {voice.error && (
          <p className="mt-2 text-xs font-semibold text-red-600 bg-red-50 px-3 py-1 rounded-full border border-red-200">
            {voice.error}
          </p>
        )}

        {/* Versatile command quick test chips */}
        <div className="mt-5 flex flex-wrap justify-center gap-2 max-w-2xl">
          {quickChips.map((chip, i) => (
            <button
              key={i}
              onClick={() => voice.sendText(chip.text)}
              disabled={isBusy}
              className="rounded-full bg-slate-100 hover:bg-slate-200 border border-slate-200 px-3 py-1 text-xs font-medium text-slate-700 transition"
            >
              💬 {chip.label}: &quot;{chip.text}&quot;
            </button>
          ))}
        </div>
      </div>

      {/* Floating Pending Draft Confirmation Card */}
      {voice.draft && (
        <div
          className={`card mb-6 border-2 shadow-lg animate-in slide-in-from-top-4 ${
            voice.draft.anomaly_warning
              ? "border-red-500 bg-red-50/95"
              : "border-amber-400 bg-amber-50/90"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold uppercase ${
                voice.draft.anomaly_warning
                  ? "bg-red-200 text-red-900"
                  : "bg-amber-200 text-amber-900"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full animate-pulse ${
                  voice.draft.anomaly_warning ? "bg-red-600" : "bg-amber-600"
                }`}
              />
              {voice.draft.anomaly_warning
                ? "⚠️ High Amount Safety Alert — Double Check!"
                : "Confirmation Required: Guardrail Enforced"}
            </span>
            <span className="text-xs font-semibold text-amber-800">Say &quot;Confirm&quot; / &quot;Haan&quot; / &quot;Houdu&quot;</span>
          </div>

          {voice.draft.anomaly_warning && voice.draft.warning_message && (
            <p className="mt-2 rounded-lg bg-red-100 border border-red-300 px-3 py-1.5 text-xs font-bold text-red-800">
              {voice.draft.warning_message}
            </p>
          )}

          <div className="my-3">
            <div className="flex flex-wrap items-baseline gap-2">
              <p className="text-2xl font-extrabold text-slate-900">
                {voice.draft.customer}
              </p>
              {voice.draft.member_name && (
                <span className="inline-flex items-center gap-1 text-xs font-bold bg-amber-200 text-amber-900 px-2.5 py-0.5 rounded-full border border-amber-300">
                  👤 {voice.draft.relationship ? `${voice.draft.relationship}: ` : "Member: "}{voice.draft.member_name}
                </span>
              )}
              <span
                className={
                  voice.draft.type === "credit"
                    ? "text-red-600 text-2xl font-extrabold"
                    : voice.draft.type === "adjustment"
                    ? "text-purple-700 text-2xl font-extrabold"
                    : "text-emerald-600 text-2xl font-extrabold"
                }
              >
                {voice.draft.type === "credit"
                  ? "Udhar (Credit)"
                  : voice.draft.type === "adjustment"
                  ? `Adjustment (${voice.draft.adjustment_reason || "discount"})`
                  : "Paid (Jama)"}{" "}
                {inr(voice.draft.amount)}
              </span>
            </div>

            {/* Rule warning red banner with exact written rule text */}
            {voice.draft.rule_warnings && voice.draft.rule_warnings.length > 0 && (
              <div className="mt-3 rounded-xl bg-red-100 border-2 border-red-400 p-3.5 text-red-950 shadow-sm">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-black uppercase tracking-wide text-red-800 flex items-center gap-1.5">
                    <span>🚨 Dukaan Rule Policy Alert</span>
                  </p>
                  <span className="text-[10px] font-bold bg-red-200 text-red-900 px-2 py-0.5 rounded-full">
                    Override Required
                  </span>
                </div>
                <div className="mt-2 space-y-2">
                  {voice.draft.rule_warnings.map((rw: any, idx: number) => (
                    <div key={idx} className="rounded-lg bg-white/90 p-2.5 border border-red-300 text-xs shadow-sm">
                      <p className="font-extrabold text-red-900 flex items-center gap-1 flex-wrap">
                        <span>📜 Written Dukaan Rule:</span>
                        <span className="italic underline">&quot;{rw.rule_text || rw.message}&quot;</span>
                      </p>
                      {rw.message && rw.rule_text && (
                        <p className="text-[11px] text-red-700 mt-1 font-semibold">{rw.message}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Pending Promise Alert Amber Banner */}
            {(voice.draft.promise_warning || voice.draft.pending_promise) && (
              <div className="mt-3 rounded-xl bg-amber-100 border-2 border-amber-400 p-3.5 text-amber-950 shadow-sm animate-in slide-in-from-top-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-black uppercase tracking-wide text-amber-900 flex items-center gap-1.5">
                    <span>⚠️ Pending Payment Promise Alert</span>
                  </p>
                  <span className="text-[10px] font-bold bg-amber-200 text-amber-900 px-2 py-0.5 rounded-full uppercase">
                    {voice.draft.pending_promise?.status || "PENDING"}
                  </span>
                </div>
                <div className="mt-2 rounded-lg bg-white/95 p-2.5 border border-amber-300 text-xs shadow-sm">
                  <p className="font-extrabold text-amber-900 flex items-center gap-1.5 flex-wrap">
                    <span>🤝 Existing Promise to Pay:</span>
                    <span className="underline">
                      {voice.draft.pending_promise?.promised_amount
                        ? inr(voice.draft.pending_promise.promised_amount)
                        : "Purana hisaab"}{" "}
                      by {voice.draft.pending_promise?.expected_date}
                    </span>
                  </p>
                  {voice.draft.pending_promise?.description && (
                    <p className="text-[11px] text-amber-800 mt-1 font-medium">
                      Note: &quot;{voice.draft.pending_promise.description}&quot;
                    </p>
                  )}
                  <p className="text-[11px] text-amber-900 mt-1.5 font-bold bg-amber-50 p-1.5 rounded border border-amber-200">
                    Customer is asking for additional credit of {inr(voice.draft.amount)}. Confirm below to give more credit, or cancel to collect payment first.
                  </p>
                </div>
              </div>
            )}

            {/* Quick Add WhatsApp option right below name ONLY if customer has no WhatsApp registered */}
            {!voice.draft.customer_phone && voice.draft.customer_id && (
              <div className="mt-2">
                {draftWaSaved ? (
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-bold text-emerald-700">✓ WhatsApp saved: {draftWaSaved}</span>
                    <a
                      href={whatsAppReminderUrl(
                        draftWaSaved,
                        voice.draft.customer,
                        voice.draft.projected_balance ?? voice.draft.amount,
                        shop?.name || "Kirana Store"
                      )}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded-full bg-emerald-600 px-2.5 py-0.5 font-bold text-white hover:bg-emerald-700"
                    >
                      💬 Send Loan Info on WhatsApp
                    </a>
                  </div>
                ) : draftWaOpen ? (
                  <form
                    className="flex flex-wrap items-center gap-1.5"
                    onSubmit={async (e) => {
                      e.preventDefault();
                      const cleaned = draftWaNum.trim();
                      if (!cleaned || !voice.draft?.customer_id) return;
                      await api.updateCustomer(voice.draft.customer_id, { phone: cleaned });
                      setDraftWaSaved(cleaned);
                      setDraftWaOpen(false);
                    }}
                  >
                    <input
                      type="tel"
                      inputMode="tel"
                      autoFocus
                      required
                      placeholder="Enter 10-digit WhatsApp #"
                      value={draftWaNum}
                      onChange={(e) => setDraftWaNum(e.target.value)}
                      className="rounded-lg border border-emerald-400 bg-white px-2.5 py-1 text-xs font-medium text-slate-900 w-44"
                    />
                    <button
                      type="submit"
                      className="rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-bold text-white hover:bg-emerald-700"
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setDraftWaOpen(false)}
                      className="rounded-lg bg-white border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-600"
                    >
                      Cancel
                    </button>
                  </form>
                ) : (
                  <button
                    type="button"
                    onClick={() => setDraftWaOpen(true)}
                    className="inline-flex items-center gap-1 rounded-full bg-white border border-emerald-400 px-2.5 py-0.5 text-xs font-bold text-emerald-700 hover:bg-emerald-50 transition"
                  >
                    <span>📱</span>
                    <span>+ Add WhatsApp Number (for loan info)</span>
                  </button>
                )}
              </div>
            )}

            {/* Metadata pills: Payment Mode, Dates, Projected Balance / Advance */}
            <div className="mt-2 flex flex-wrap gap-1.5 text-xs font-semibold">
              {voice.draft.payment_mode && (
                <span className="rounded-full bg-blue-100 text-blue-800 px-2.5 py-0.5">
                  {voice.draft.payment_mode === "upi" ? "📱 UPI" : voice.draft.payment_mode === "cash" ? "💵 Cash" : "💳 Other"}
                </span>
              )}
              {voice.draft.due_date && (
                <span className="rounded-full bg-amber-100 text-amber-900 px-2.5 py-0.5">
                  📅 Due: {voice.draft.due_date}
                </span>
              )}
              {voice.draft.backdated_to && (
                <span className="rounded-full bg-slate-200 text-slate-700 px-2.5 py-0.5">
                  ⏪ Backdated: {voice.draft.backdated_to}
                </span>
              )}
              {typeof voice.draft.projected_balance === "number" && (
                <span
                  className={`rounded-full px-2.5 py-0.5 ${
                    voice.draft.projected_balance < 0
                      ? "bg-teal-100 text-teal-800"
                      : "bg-slate-100 text-slate-700"
                  }`}
                >
                  {voice.draft.projected_balance < 0
                    ? `Advance (Shop owes ${inr(Math.abs(voice.draft.projected_balance))})`
                    : `New Balance: ${inr(voice.draft.projected_balance)}`}
                </span>
              )}
            </div>

            {voice.draft.items && voice.draft.items.length > 0 && (
              <div className="mt-2 rounded-lg bg-white/80 border border-slate-200 p-2 text-xs text-slate-700">
                <p className="font-bold text-slate-600 mb-1">Items:</p>
                <ul className="list-disc pl-4 space-y-0.5">
                  {voice.draft.items.map((it, idx) => (
                    <li key={idx}>
                      {it.qty ? `${it.qty} ` : ""}
                      {it.name}
                      {it.amount ? ` — ${inr(it.amount)}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {voice.draft.item_note && (
              <p className="mt-1.5 text-xs text-slate-700 font-semibold">📦 Item Note: {voice.draft.item_note}</p>
            )}

            {voice.draft.note && (
              <p className="mt-1.5 text-xs text-slate-600 font-medium">Note: {voice.draft.note}</p>
            )}
          </div>

          <div className="flex flex-wrap gap-3">
            {voice.draft.requires_override ? (
              <>
                <button
                  className="btn flex-1 bg-red-600 text-white font-bold py-3 hover:bg-red-700 shadow-md text-sm"
                  onClick={() => voice.sendText("Continue anyway")}
                >
                  ⚠️ Continue anyway (Override Rule)
                </button>
                <button
                  className="btn flex-1 bg-white text-slate-700 border border-slate-300 font-bold py-3 hover:bg-slate-50 text-sm"
                  onClick={() => voice.sendText("No, cancel this")}
                >
                  Change amount / Cancel
                </button>
              </>
            ) : (
              <>
                <button
                  className="btn flex-1 bg-emerald-600 text-white font-bold py-3 hover:bg-emerald-700 shadow-md text-sm"
                  onClick={() => voice.sendText("Yes, confirm")}
                >
                  ✓ Confirm (Commit to Ledger)
                </button>
                <button
                  className="btn flex-1 bg-white text-red-600 border border-red-300 font-bold py-3 hover:bg-red-50 text-sm"
                  onClick={() => voice.sendText("No, cancel this")}
                >
                  ✕ Cancel Draft
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Promise Recorded or Pending Promise Alert Card */}
      {voice.promiseCard && (
        <div className={`card mb-6 border-2 shadow-md animate-in slide-in-from-top-4 ${
          voice.promiseCard.alert
            ? "border-amber-400 bg-amber-50/95"
            : "border-blue-400 bg-blue-50/95"
        }`}>
          <div className="flex items-center justify-between">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold uppercase ${
              voice.promiseCard.alert
                ? "bg-amber-200 text-amber-950"
                : "bg-blue-200 text-blue-900"
            }`}>
              {voice.promiseCard.alert ? "⚠️ Pending Promise Alert" : "🤝 Promise Recorded"}
            </span>
            <button
              onClick={voice.clearPromiseCard}
              className="text-xs font-semibold text-slate-500 hover:text-slate-700"
            >
              Dismiss ✕
            </button>
          </div>
          <div className="my-2.5">
            <p className="text-xl font-black text-slate-900">
              {voice.promiseCard.customer_name || voice.promiseCard.entity_name} • {voice.promiseCard.amount ? inr(voice.promiseCard.amount) : voice.promiseCard.description}
            </p>
            <p className={`text-xs font-bold mt-1 ${voice.promiseCard.alert ? "text-amber-900" : "text-blue-800"}`}>
              📅 Expected Date: {voice.promiseCard.expected_date}
            </p>
            {voice.promiseCard.new_amount && (
              <p className="text-xs font-bold text-amber-950 mt-1 bg-white/80 p-1.5 rounded border border-amber-300">
                ⚠️ Asking for additional {inr(voice.promiseCard.new_amount)} udhar. Existing promise is still pending.
              </p>
            )}
            <p className="text-xs text-slate-600 mt-1">
              🔒 Note: Customer ledger balance remains unchanged until payment is actually confirmed.
            </p>
          </div>
        </div>
      )}

      {/* Purple Shop Rule Saved Card */}
      {voice.ruleCard && (
        <div className="card mb-6 border-2 border-purple-400 bg-purple-50/95 shadow-md animate-in slide-in-from-top-4">
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-purple-200 text-purple-900 px-2.5 py-0.5 text-xs font-bold uppercase">
              📜 Dukaan Policy Rule Saved
            </span>
            <button
              onClick={voice.clearRuleCard}
              className="text-xs font-semibold text-slate-500 hover:text-slate-700"
            >
              Dismiss ✕
            </button>
          </div>
          <div className="my-2.5">
            <p className="text-base font-extrabold text-slate-900">&quot;{voice.ruleCard.rule_text}&quot;</p>
            <span className="inline-block mt-1 text-xs font-semibold text-purple-800 bg-purple-100 border border-purple-200 px-2 py-0.5 rounded-md">
              Category: {voice.ruleCard.rule_category}
            </span>
          </div>
          <div className="mt-2 flex gap-2">
            <button
              onClick={async () => {
                if (voice.ruleCard?.rule_id) {
                  await api.deleteRule(voice.ruleCard.rule_id);
                  voice.clearRuleCard();
                }
              }}
              className="btn bg-white text-purple-700 border border-purple-300 text-xs px-3 py-1.5 hover:bg-purple-100 font-bold"
            >
              Undo / Delete Rule
            </button>
          </div>
        </div>
      )}

      {/* Green/Orange Reconciliation Result Card */}
      {voice.reconcileResult && (
        <div
          className={`card mb-6 border-2 shadow-md animate-in slide-in-from-top-4 ${
            voice.reconcileResult.status === "MATCHED"
              ? "border-emerald-500 bg-emerald-50/95"
              : "border-amber-500 bg-amber-50/95"
          }`}
        >
          <div className="flex items-center justify-between">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold uppercase ${
                voice.reconcileResult.status === "MATCHED"
                  ? "bg-emerald-200 text-emerald-900"
                  : "bg-amber-200 text-amber-900"
              }`}
            >
              {voice.reconcileResult.status === "MATCHED" ? "✓ Khata Reconciled: Matched" : "⚠️ Needs Investigation"}
            </span>
            <button
              onClick={voice.clearReconcileResult}
              className="text-xs font-semibold text-slate-500 hover:text-slate-700"
            >
              Dismiss ✕
            </button>
          </div>
          <div className="my-2 text-xs text-slate-800 space-y-1 font-medium">
            <p>
              Cash Difference: <b>{inr(voice.reconcileResult.cash_difference ?? 0)}</b> | UPI Difference:{" "}
              <b>{inr(voice.reconcileResult.upi_difference ?? 0)}</b>
            </p>
            {voice.reconcileResult.findings && voice.reconcileResult.findings.length > 0 && (
              <div className="mt-2 rounded-lg bg-white/80 border border-amber-200 p-2.5">
                <p className="font-bold text-amber-900 mb-1">Diagnostic Findings:</p>
                <ul className="list-disc pl-4 space-y-1 text-slate-700">
                  {voice.reconcileResult.findings.map((f: any, i: number) => (
                    <li key={i}>{f.message}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* WhatsApp Payment Reminder Card */}
      {voice.reminder && (
        <div className="card mb-6 border-2 border-emerald-400 bg-emerald-50/90 shadow-md">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase text-emerald-800">
              📲 Payment Reminder Ready
            </span>
            <button
              onClick={voice.clearReminder}
              className="text-xs font-semibold text-slate-500 hover:text-slate-700"
            >
              Dismiss
            </button>
          </div>
          <p className="mt-2 text-sm font-bold text-slate-900">
            {voice.reminder.customer} — Pending {inr(voice.reminder.balance)}
          </p>
          <p className="mt-1 text-xs text-slate-600">{voice.reminder.reminder_text}</p>
          <a
            href={voice.reminder.whatsapp_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow hover:bg-emerald-700 transition"
          >
            💬 Open WhatsApp Reminder
          </a>
        </div>
      )}

      {/* Live Conversation Transcript Display with Speaker audio replay */}
      <div className="card mb-4 min-h-[14rem] max-h-[22rem] overflow-y-auto space-y-3 bg-white p-5 border-slate-200">
        {voice.msgs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-center text-slate-400">
            <span className="text-4xl mb-2">🎙️</span>
            <p className="text-sm font-semibold text-slate-600">Your live voice conversation will appear here</p>
            <p className="text-xs text-slate-400 mt-1 max-w-sm">
              Supports any language &amp; accent: Kannada, Hindi, Hinglish, English, Tamil, Telugu, etc.
              New customers are automatically registered in your khata!
            </p>
          </div>
        ) : (
          voice.msgs.map((m, i) => {
            const isYou = m.role === "you";
            return (
              <div key={i} className={`flex ${isYou ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm shadow-sm ${
                    isYou
                      ? m.silent
                        ? "bg-slate-100 text-slate-500 border border-dashed border-slate-300 rounded-br-sm italic"
                        : "bg-emerald-600 text-white rounded-br-sm"
                      : "bg-slate-100 text-slate-900 border border-slate-200 rounded-bl-sm"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3 mb-0.5">
                    <p className="text-[10px] font-semibold opacity-75">
                      {isYou
                        ? m.silent
                          ? "👂 Counter context (noted silently)"
                          : "You"
                        : "DukaanAI (Hi Khata)"}
                    </p>
                    {!isYou && m.audio && (
                      <button
                        onClick={() => voice.playAudio(m.audio!)}
                        title="Replay Voice Audio"
                        className="text-xs opacity-75 hover:opacity-100 hover:scale-110 transition"
                      >
                        🔊 Listen
                      </button>
                    )}
                  </div>
                  <p className="whitespace-pre-wrap">{m.text}</p>
                </div>
              </div>
            );
          })
        )}
        <div ref={endRef} />
      </div>

      {/* Text Input Fallback */}
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (typedText.trim()) {
            voice.sendText(typedText);
            setTypedText("");
          }
        }}
      >
        <input
          className="input shadow-sm"
          placeholder="Or type an entry (e.g. 'Pooja Sharma 450 udhar' or 'Aaj ka total hisab')…"
          value={typedText}
          onChange={(e) => setTypedText(e.target.value)}
        />
        <button className="btn bg-emerald-600 text-white hover:bg-emerald-700 px-5 shadow-sm" disabled={isBusy}>
          Send
        </button>
        <button
          type="button"
          className="btn bg-slate-100 text-slate-700 hover:bg-slate-200 px-4"
          onClick={voice.reset}
        >
          Reset
        </button>
      </form>
    </>
  );
}
