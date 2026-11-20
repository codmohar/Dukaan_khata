"use client";
import { useEffect, useRef, useState } from "react";
import { api, Customer, inr, ScanData, ScanLine, scans } from "@/lib/api";
import { ErrorBanner, PageTitle } from "@/components/ui";

/** Shrinks big phone photos to ~2000 px JPEG so uploads are fast and stay under the 8 MB limit. */
async function shrink(file: File): Promise<Blob> {
  const bmp = await createImageBitmap(file);
  const k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * k);
  c.height = Math.round(bmp.height * k);
  c.getContext("2d")!.drawImage(bmp, 0, 0, c.width, c.height);
  return new Promise((res, rej) =>
    c.toBlob((b) => (b ? res(b) : rej(new Error("Image processing error"))), "image/jpeg", 0.85)
  );
}

const HINTS: [string, string][] = [
  ["", "Auto-detect document type"],
  ["khata_page", "Khata / udhar page"],
  ["payment_proof", "UPI / payment screenshot"],
  ["supplier_bill", "Supplier bill (payable reference)"],
];

export default function ScanPage() {
  const [data, setData] = useState<ScanData | null>(null);
  const [preview, setPreview] = useState("");
  const [hint, setHint] = useState("");
  const [custs, setCusts] = useState<Customer[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.customers().then(setCusts).catch(() => {});
  }, []);

  async function onFile(f?: File) {
    if (!f) return;
    setErr("");
    setDone("");
    setData(null);
    setBusy(true);
    try {
      const blob = await shrink(f);
      setPreview(URL.createObjectURL(blob));
      const res = await scans.upload(blob, hint || undefined);
      setData(res);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function edit(id: string, patch: Record<string, unknown>) {
    try {
      const upd = await scans.editLine(id, patch);
      setData((d) => d && { ...d, lines: d.lines.map((l) => (l.id === id ? upd : l)) });
      if (patch.create_customer_name) api.customers().then(setCusts);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function approve() {
    if (!data) return;
    try {
      const r = await scans.approve(data.scan.id);
      setDone(`✓ ${r.created} entries successfully approved and added to your khata ledger!`);
      setData(null);
      setPreview("");
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function discard() {
    if (data) {
      await scans.reject(data.scan.id).catch(() => {});
      setData(null);
      setPreview("");
    }
  }

  const included = data?.lines.filter((l) => l.include) ?? [];
  const unresolved = included.filter((l) => !l.customer_id).length;

  return (
    <>
      <PageTitle
        title="Scan Book &amp; Photos"
        sub="Photograph a khata page, UPI screenshot or supplier bill: AI extracts entries, you review, then save"
      />

      <ErrorBanner msg={err} onClose={() => setErr("")} />
      {done && (
        <div className="mb-4 rounded-xl bg-emerald-50 border border-emerald-200 p-4 text-sm font-bold text-emerald-800 shadow-sm animate-in fade-in">
          {done}
        </div>
      )}

      {!data && (
        <div className="card flex flex-col items-center gap-4 py-12 text-center bg-gradient-to-b from-white to-slate-50 shadow-sm border border-slate-200">
          <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-emerald-100 text-4xl shadow-inner">
            📷
          </div>
          <div>
            <h2 className="text-xl font-black text-slate-900">Scan Khata Book or Payment Proof</h2>
            <p className="max-w-md text-xs text-slate-500 mt-1">
              Flat page, good light, whole page in frame. Photos are processed directly for OCR and never stored on the server.
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-2 mt-2">
            <select
              className="input !w-auto bg-slate-50 font-semibold text-xs"
              value={hint}
              onChange={(e) => setHint(e.target.value)}
            >
              {HINTS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>

            <input
              ref={input}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => onFile(e.target.files?.[0])}
            />
            <button
              className="btn bg-emerald-600 text-white font-bold hover:bg-emerald-700 shadow-md text-sm px-6 py-2.5"
              disabled={busy}
              onClick={() => input.current?.click()}
            >
              {busy ? "Reading document photo…" : "📷 Take Photo / Upload Image"}
            </button>
          </div>
        </div>
      )}

      {data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_1.6fr]">
          <div className="card h-fit lg:sticky lg:top-4 border border-slate-200 p-4 shadow-sm">
            <h3 className="font-bold text-slate-900 text-sm mb-2">Original Document Photo</h3>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={preview} alt="Scanned page" className="w-full rounded-xl border border-slate-200 shadow-sm object-contain max-h-[70vh]" />
            <p className="mt-3 text-xs font-semibold text-slate-700 bg-slate-50 p-2.5 rounded-lg border border-slate-200">
              {data.scan.summary || "Document processed successfully."}
            </p>
            {data.scan.total_shown && (
              <p className="mt-2 text-xs font-bold text-slate-600">
                Printed / Written Total: <span className="text-slate-900">{inr(data.scan.total_shown)}</span>
              </p>
            )}
          </div>

          <div className="space-y-4">
            {data.scan.warnings.map((w, i) => (
              <div key={i} className="rounded-xl border border-amber-300 bg-amber-50 p-3.5 text-xs font-semibold text-amber-900 shadow-sm">
                ⚠️ {w}
              </div>
            ))}

            {data.lines.length === 0 && (
              <div className="card text-sm text-slate-500 text-center py-10">
                No ledger credit/payment entries detected in this image.
              </div>
            )}

            <div className="space-y-3">
              {data.lines.map((l) => (
                <LineCard key={l.id} l={l} custs={custs} edit={edit} />
              ))}
            </div>

            <div className="sticky bottom-4 bg-white/95 backdrop-blur-md p-4 rounded-2xl border border-slate-200 shadow-xl flex gap-3 z-20">
              <button
                className="btn flex-1 bg-emerald-600 text-white font-bold py-3 hover:bg-emerald-700 shadow-md text-sm disabled:opacity-50"
                disabled={included.length === 0 || unresolved > 0}
                onClick={approve}
              >
                {unresolved > 0
                  ? `Select a customer for ${unresolved} highlighted line(s)`
                  : `✓ Approve & Commit ${included.length} Entries to Ledger`}
              </button>
              <button
                className="btn bg-white text-red-600 border border-red-300 font-bold px-5 hover:bg-red-50 text-sm"
                onClick={discard}
              >
                Discard
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function LineCard({
  l,
  custs,
  edit,
}: {
  l: ScanLine;
  custs: Customer[];
  edit: (id: string, p: Record<string, unknown>) => void;
}) {
  const low = l.confidence < 0.6;
  const missingCustomer = l.include && !l.customer_id;

  return (
    <div
      className={`card !p-4 transition-all duration-150 ${
        !l.include ? "opacity-50 bg-slate-50" : missingCustomer ? "border-2 border-red-400 bg-red-50/30" : low ? "border-amber-300 bg-amber-50/20" : "bg-white"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs text-slate-600 font-medium">
          Line {l.raw_text ? `read as: “${l.raw_text}”` : ""}
          {low && <span className="ml-1 text-amber-700 font-bold">· ⚠️ low confidence handwriting</span>}
        </p>
        <label className="flex items-center gap-1.5 text-xs font-bold cursor-pointer text-slate-700">
          <input
            type="checkbox"
            className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
            checked={l.include}
            onChange={(e) => edit(l.id, { include: e.target.checked })}
          />
          Include
        </label>
      </div>

      {l.duplicate && (
        <p className="mt-1 text-xs font-bold text-amber-800 bg-amber-100/80 px-2.5 py-1 rounded-md">
          ⚠️ Possible duplicate: same customer, amount, and date already exists in ledger. Unchecked by default.
        </p>
      )}

      {missingCustomer && (
        <p className="mt-1 text-xs font-bold text-red-700">
          * Please select an existing customer or tap ＋ Add new customer to approve.
        </p>
      )}

      <div className="mt-3 grid gap-2 sm:grid-cols-[1.5fr_1fr_1fr]">
        <select
          className={`input text-xs font-semibold ${missingCustomer ? "border-red-400 ring-2 ring-red-200" : ""}`}
          value={l.customer_id ?? ""}
          onChange={(e) => {
            if (e.target.value === "__new") {
              edit(l.id, { create_customer_name: l.raw_name || "New customer" });
            } else {
              edit(l.id, { customer_id: e.target.value || null });
            }
          }}
        >
          <option value="">{l.raw_name ? `Assign “${l.raw_name}” to…` : "-- Pick Customer --"}</option>
          {l.candidates.length > 0 && (
            <optgroup label="Best Matches (Fuzzy Search)">
              {l.candidates.map((c) => (
                <option key={c.customer_id} value={c.customer_id}>
                  {c.name} {c.landmark ? `(${c.landmark})` : ""}
                </option>
              ))}
            </optgroup>
          )}
          <optgroup label="All Shop Customers">
            {custs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} {c.landmark ? `(${c.landmark})` : ""}
              </option>
            ))}
          </optgroup>
          {l.raw_name && <option value="__new">＋ Add “{l.raw_name}” as brand new customer</option>}
        </select>

        <select
          className="input text-xs font-semibold"
          value={l.type}
          onChange={(e) => edit(l.id, { type: e.target.value })}
        >
          <option value="credit">Udhar (Credit / Owes)</option>
          <option value="payment">Jama (Payment Received)</option>
        </select>

        <input
          className="input text-xs font-bold text-slate-900"
          type="number"
          min="1"
          defaultValue={Number(l.amount)}
          key={String(l.amount)}
          onBlur={(e) =>
            Number(e.target.value) > 0 &&
            Number(e.target.value) !== Number(l.amount) &&
            edit(l.id, { amount: Number(e.target.value) })
          }
        />
      </div>

      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <input
          className="input text-xs"
          type="date"
          value={l.txn_date ?? ""}
          onChange={(e) => edit(l.id, { txn_date: e.target.value || null })}
        />
        <input
          className="input text-xs"
          placeholder="Note / items"
          defaultValue={l.note ?? ""}
          onBlur={(e) => e.target.value !== (l.note ?? "") && edit(l.id, { note: e.target.value })}
        />
      </div>
    </div>
  );
}

