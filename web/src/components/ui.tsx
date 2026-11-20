import React from "react";
import { useRealtimeStatus } from "@/lib/supabase";

export function PageTitle({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children?: React.ReactNode;
}) {
  const isRealtime = useRealtimeStatus();

  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 md:text-3xl">{title}</h1>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
              isRealtime
                ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                : "bg-slate-100 text-slate-600 border border-slate-300"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                isRealtime ? "bg-emerald-500 animate-pulse" : "bg-slate-400"
              }`}
            />
            {isRealtime ? "Live Sync" : "Sync (5s)"}
          </span>
        </div>
        {sub && <p className="mt-1 text-sm text-slate-500">{sub}</p>}
      </div>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}

export function Stat({
  label,
  value,
  tone = "default",
  subtext,
}: {
  label: string;
  value: string | number;
  tone?: "default" | "red" | "green" | "amber";
  subtext?: string;
}) {
  const colorMap = {
    red: "text-red-600",
    green: "text-emerald-600",
    amber: "text-amber-600",
    default: "text-slate-900",
  };

  return (
    <div className="card transition hover:border-slate-300 hover:shadow-md">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`mt-1.5 text-2xl font-extrabold md:text-3xl ${colorMap[tone]}`}>{value}</p>
      {subtext && <p className="mt-1 text-xs text-slate-400">{subtext}</p>}
    </div>
  );
}

export function Badge({ status }: { status: string }) {
  const m: Record<string, string> = {
    confirmed: "bg-emerald-100 text-emerald-800 border border-emerald-300",
    draft: "bg-amber-100 text-amber-800 border border-amber-300",
    cancelled: "bg-slate-100 text-slate-600 border border-slate-300",
    credit: "bg-red-100 text-red-800 border border-red-300",
    payment: "bg-emerald-100 text-emerald-800 border border-emerald-300",
    adjustment: "bg-purple-100 text-purple-800 border border-purple-300",
  };

  const label =
    status === "credit"
      ? "Udhar (Credit)"
      : status === "payment"
      ? "Jama (Payment)"
      : status === "adjustment"
      ? "Adjustment"
      : status === "draft"
      ? "Awaiting Confirm"
      : status;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${
        m[status] ?? "bg-slate-100 text-slate-700"
      }`}
    >
      {label}
    </span>
  );
}

export function ErrorBanner({ msg, onClose }: { msg: string; onClose?: () => void }) {
  if (!msg) return null;
  return (
    <div className="mb-4 flex items-center justify-between rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 shadow-sm">
      <div className="flex items-center gap-2">
        <span className="text-base">⚠️</span>
        <span>{msg}</span>
      </div>
      {onClose && (
        <button onClick={onClose} className="text-xs font-semibold text-red-600 hover:text-red-900">
          Dismiss
        </button>
      )}
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-in fade-in">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl border border-slate-200">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-900">{title}</h3>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export const LANGS = [
  { code: "kn-IN", label: "ಕನ್ನಡ (Kannada)", hint: "Ramesh ge 340 rupayi udhar bardu" },
  { code: "hi-IN", label: "हिन्दी (Hindi)", hint: "Ramesh ka 340 rupaye udhar likho" },
  { code: "en-IN", label: "English", hint: "Add 340 rupees credit for Ramesh" },
  { code: "ta-IN", label: "தமிழ் (Tamil)", hint: "Ramesh ku 340 roobai kadan ezhudhu" },
  { code: "te-IN", label: "తెలుగు (Telugu)", hint: "Ramesh ki 340 rupayalu appu raayi" },
  { code: "mr-IN", label: "मराठी (Marathi)", hint: "Ramesh chya navavar 340 rupaye udhari liha" },
  { code: "bn-IN", label: "বাংলা (Bengali)", hint: "Ramesh er naame 340 taka baki lekho" },
  { code: "gu-IN", label: "ગુજરાતી (Gujarati)", hint: "Ramesh na naame 340 rupiya udhar lakho" },
  { code: "ml-IN", label: "മലയാളം (Malayalam)", hint: "Ramesh inu 340 roopa kadam ezhuthikko" },
  { code: "pa-IN", label: "ਪੰਜਾਬੀ (Punjabi)", hint: "Ramesh de naam 340 rupaye udhaar likh lo" },
  { code: "or-IN", label: "ଓଡ଼ିଆ (Odia)", hint: "Ramesh ku 340 tanka udhaar likhi dia" },
  { code: "as-IN", label: "অসমীয়া (Assamese)", hint: "Ramesh or naamot 340 toka baki likha" },
  { code: "ur-IN", label: "اردو (Urdu)", hint: "Ramesh ke khaate mein 340 rupay udhaar likhiye" },
];

export const I18N = {
  "en-IN": {
    promises_title: "Today's Promises & Evening Reconciliation",
    start_reconciliation: "Start Evening Reconciliation",
    reconciled_today: "Reconciled Today ✓",
    overdue: "Overdue",
    promise_recorded: "Promise Recorded",
    rule_saved: "Dukaan Rule Policy Saved",
    rule_warning: "Dukaan Rule Policy Warning",
    continue_override: "Continue anyway (Override Rule)",
    change_amount: "Change amount / Cancel",
    matched: "Khata Matched",
    needs_investigation: "Needs Investigation",
    household_khata: "Household Account",
    dispute_timeline: "Smart Dispute Timeline",
    ask_memory: "Ask memory: recall promises, past transactions, or rules...",
  },
  "hi-IN": {
    promises_title: "आज के वादे और शाम का हिसाब मिलान",
    start_reconciliation: "शाम का हिसाब मिलान शुरू करें",
    reconciled_today: "आज का हिसाब मिल गया ✓",
    overdue: "तारीख निकल गई",
    promise_recorded: "वादा दर्ज हो गया",
    rule_saved: "दुकान का नियम सुरक्षित हुआ",
    rule_warning: "दुकान नियम चेतावनी",
    continue_override: "फिर भी जारी रखें (नियम बदलें)",
    change_amount: "रकम बदलें / रद्द करें",
    matched: "खाता एकदम सही मिला",
    needs_investigation: "जाँच की ज़रूरत है",
    household_khata: "पारिवारिक खाता",
    dispute_timeline: "स्मार्ट विवाद समयरेखा",
    ask_memory: "मेमोरी से पूछें: वादे, पुराने लेन-देन या नियम...",
  },
  "kn-IN": {
    promises_title: "ಇಂದಿನ ಮಾತುಗಳು ಮತ್ತು ಸಂಜೆಯ ಲೆಕ್ಕ ಪರಿಶೀಲನೆ",
    start_reconciliation: "ಸಂಜೆಯ ಲೆಕ್ಕ ಪರಿಶೀಲನೆ ಪ್ರಾರಂಭಿಸಿ",
    reconciled_today: "ಇಂದಿನ ಲೆಕ್ಕ ಸರಿಯಾಗಿದೆ ✓",
    overdue: "ದಿನ ಮೀರಿದೆ",
    promise_recorded: "ಮಾತು ದಾಖಲಾಗಿದೆ",
    rule_saved: "ಅಂಗಡಿ ನಿಯಮ ಉಳಿಸಲಾಗಿದೆ",
    rule_warning: "ಅಂಗಡಿ ನಿಯಮ ಎಚ್ಚರಿಕೆ",
    continue_override: "ಹಾಗೆಯೇ ಮುಂದುವರಿಸಿ (ನಿಯಮ ಮೀರಿ)",
    change_amount: "ಮೊತ್ತ ಬದಲಿಸಿ / ರದ್ದುಮಾಡಿ",
    matched: "ಖಾತೆ ಸರಿಯಾಗಿ ಸರಿಹೊಂದಿದೆ",
    needs_investigation: "ಪರಿಶೀಲನೆ ಅಗತ್ಯವಿದೆ",
    household_khata: "ಕುಟುಂಬದ ಖಾತೆ",
    dispute_timeline: "ವಿವಾದ ಪರಿಹಾರ ಟೈಮ್‌ಲೈನ್",
    ask_memory: "ನೆನಪಿನಿಂದ ಕೇಳಿ: ಮಾತುಗಳು, ಹಳೆಯ ಲೆಕ್ಕ ಅಥವಾ ನಿಯಮಗಳು...",
  },
};
