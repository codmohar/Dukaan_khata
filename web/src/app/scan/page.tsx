"use client";
import { useEffect, useRef, useState } from "react";
import { api, Customer, inr, ScanData, ScanLine, scans } from "@/lib/api";
import { ErrorBanner, PageTitle } from "@/components/ui";

/** Shrinks big phone photos to ~2000 px JPEG so uploads are fast and stay under the 8 MB limit. */
async function shrink(file: File | Blob): Promise<Blob> {
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

  // Camera Viewfinder Modal State
  const [cameraOpen, setCameraOpen] = useState(false);
  const [facingMode, setFacingMode] = useState<"environment" | "user">("environment");
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Hidden native inputs
  const galleryInput = useRef<HTMLInputElement>(null);
  const nativeCamInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.customers().then(setCusts).catch(() => {});
  }, []);

  // Clean up camera stream on unmount
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  };

  const startCamera = async (mode: "environment" | "user" = facingMode) => {
    stopCamera();
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        // Fallback to native camera input on unsupported browsers
        nativeCamInput.current?.click();
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: mode },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      });
      streamRef.current = stream;
      setCameraOpen(true);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
    } catch {
      // Permission denied or camera unavailable -> fallback to device camera input
      stopCamera();
      setCameraOpen(false);
      nativeCamInput.current?.click();
    }
  };

  const switchCamera = () => {
    const next = facingMode === "environment" ? "user" : "environment";
    setFacingMode(next);
    startCamera(next);
  };

  const captureFrame = async () => {
    if (!videoRef.current) return;
    const v = videoRef.current;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth || 1280;
    canvas.height = v.videoHeight || 720;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(v, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(async (blob) => {
      if (blob) {
        stopCamera();
        setCameraOpen(false);
        await processBlob(blob);
      }
    }, "image/jpeg", 0.9);
  };

  async function processBlob(rawBlob: Blob) {
    setErr("");
    setDone("");
    setData(null);
    setBusy(true);
    try {
      const blob = await shrink(rawBlob);
      setPreview(URL.createObjectURL(blob));
      const res = await scans.upload(blob, hint || undefined);
      setData(res);
      api.customers().then(setCusts).catch(() => {});
      const count = res.lines.filter((l) => l.include).length;
      setDone(`✓ ${count} entries extracted and committed directly to the database & ledger!`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
      if (galleryInput.current) galleryInput.current.value = "";
      if (nativeCamInput.current) nativeCamInput.current.value = "";
    }
  }

  async function onFile(f?: File) {
    if (!f) return;
    await processBlob(f);
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
      setDone(`✓ ${r.created} entries confirmed in database and updated in your khata ledger!`);
      api.customers().then(setCusts).catch(() => {});
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

      {/* Hidden file inputs: One for pure gallery upload, one for native camera fallback */}
      <input
        ref={galleryInput}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => onFile(e.target.files?.[0])}
      />
      <input
        ref={nativeCamInput}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => onFile(e.target.files?.[0])}
      />

      {/* Live In-App Camera Viewfinder Modal */}
      {cameraOpen && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-between bg-black p-4 text-white animate-in fade-in">
          <div className="w-full flex items-center justify-between max-w-md pt-2">
            <span className="text-xs font-bold text-emerald-400 bg-emerald-950/80 px-3 py-1 rounded-full border border-emerald-500/30">
              🔴 Live Khata Viewfinder
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={switchCamera}
                className="rounded-full bg-slate-800/80 px-3 py-1.5 text-xs font-bold text-slate-200 hover:bg-slate-700"
              >
                🔄 Flip
              </button>
              <button
                onClick={() => {
                  stopCamera();
                  setCameraOpen(false);
                }}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 text-sm font-bold text-slate-300 hover:bg-slate-700"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="relative my-auto flex w-full max-w-md items-center justify-center overflow-hidden rounded-3xl border-2 border-emerald-500/50 bg-black shadow-2xl">
            <video
              ref={videoRef}
              playsInline
              autoPlay
              muted
              className="h-[65vh] w-full object-cover"
            />
            {/* Alignment Box Overlay */}
            <div className="pointer-events-none absolute inset-6 rounded-2xl border-2 border-dashed border-emerald-400/70" />
            <div className="pointer-events-none absolute bottom-4 inset-x-0 text-center">
              <span className="rounded-lg bg-black/60 px-3 py-1 text-[11px] font-medium text-emerald-300 backdrop-blur-sm">
                Hold phone flat & align document inside frame
              </span>
            </div>
          </div>

          <div className="w-full max-w-md pb-6 flex items-center justify-center gap-6">
            <button
              onClick={() => {
                stopCamera();
                setCameraOpen(false);
                galleryInput.current?.click();
              }}
              className="flex flex-col items-center gap-1 text-slate-400 hover:text-white"
            >
              <span className="text-2xl">📁</span>
              <span className="text-[10px]">Gallery</span>
            </button>

            {/* Shutter Button */}
            <button
              onClick={captureFrame}
              className="flex h-20 w-20 items-center justify-center rounded-full border-4 border-white bg-emerald-600 shadow-xl transition active:scale-90 hover:bg-emerald-500"
            >
              <div className="h-14 w-14 rounded-full bg-white shadow-inner" />
            </button>

            <button
              onClick={() => {
                stopCamera();
                setCameraOpen(false);
              }}
              className="flex flex-col items-center gap-1 text-slate-400 hover:text-white"
            >
              <span className="text-2xl">✕</span>
              <span className="text-[10px]">Cancel</span>
            </button>
          </div>
        </div>
      )}

      {/* Main Upload / Camera Launch Card */}
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

          <div className="flex flex-col items-center gap-3 mt-2 w-full max-w-md px-4">
            <div className="w-full">
              <label className="block text-left text-[11px] font-bold text-slate-600 mb-1">
                Document Type (Optional):
              </label>
              <select
                className="input bg-white font-semibold text-xs py-2"
                value={hint}
                onChange={(e) => setHint(e.target.value)}
              >
                {HINTS.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </div>

            {/* DUAL ACTION BUTTONS: CAMERA & GALLERY */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full mt-2">
              <button
                className="btn bg-emerald-600 text-white font-bold hover:bg-emerald-700 shadow-md text-sm py-3 flex items-center justify-center gap-2 active:scale-95"
                disabled={busy}
                onClick={() => startCamera()}
              >
                <span>📸</span>
                <span>{busy ? "Processing…" : "Open Live Camera"}</span>
              </button>

              <button
                className="btn bg-white text-emerald-800 border-2 border-emerald-600 font-bold hover:bg-emerald-50 shadow-sm text-sm py-3 flex items-center justify-center gap-2 active:scale-95"
                disabled={busy}
                onClick={() => galleryInput.current?.click()}
              >
                <span>📁</span>
                <span>Upload from Gallery</span>
              </button>
            </div>

            {busy && (
              <div className="flex items-center gap-2 text-xs font-bold text-emerald-700 mt-3 animate-pulse">
                <span className="h-3 w-3 rounded-full bg-emerald-500 animate-ping" />
                <span>Gemini AI is reading customer entries from photo…</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Review Screen after OCR extraction */}
      {data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_1.6fr]">
          <div className="card h-fit lg:sticky lg:top-4 border border-slate-200 p-4 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-bold text-slate-900 text-sm">Original Document Photo</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => startCamera()}
                  className="text-[11px] font-bold text-emerald-600 hover:underline"
                >
                  📸 Camera
                </button>
                <button
                  onClick={() => galleryInput.current?.click()}
                  className="text-[11px] font-bold text-slate-600 hover:underline"
                >
                  📁 Gallery
                </button>
              </div>
            </div>
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
            {data.scan.status === "approved" && (
              <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-3.5 text-xs font-bold text-emerald-900 shadow-sm flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-600 text-[10px] text-white">✓</span>
                  <span>All {included.length} entries are saved in the database and updated in your khata ledger!</span>
                </div>
                <a href="/" className="underline text-emerald-800 hover:text-emerald-950 font-bold ml-2">
                  View Ledger →
                </a>
              </div>
            )}

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

            {data.lines.map((l) => (
              <LineCard key={l.id} line={l} customers={custs} onEdit={(patch) => edit(l.id, patch)} />
            ))}

            <div className="card flex flex-wrap items-center justify-between gap-4 border border-slate-200 p-4 bg-slate-50">
              <div className="text-xs">
                <span className="font-bold text-slate-800">{included.length}</span> entries in database.
                {unresolved > 0 && (
                  <span className="ml-2 font-bold text-amber-700">
                    ⚠️ {unresolved} entry needs a customer assigned.
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={discard}
                  className="btn-ghost text-xs py-2 px-3 text-red-600 hover:bg-red-50"
                  title="Discard this scan and delete created entries from database"
                >
                  ✕ Discard
                </button>
                <button
                  onClick={() => {
                    setData(null);
                    setPreview("");
                  }}
                  className="btn bg-white border border-slate-300 text-slate-700 font-bold hover:bg-slate-100 text-xs py-2 px-3"
                >
                  📸 Scan Next Page
                </button>
                <button
                  onClick={approve}
                  disabled={included.length === 0}
                  className="btn bg-emerald-600 text-white font-bold hover:bg-emerald-700 shadow-md text-xs py-2 px-4 disabled:opacity-50"
                >
                  ✓ All Saved to Database
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function LineCard({
  line,
  customers,
  onEdit,
}: {
  line: ScanLine;
  customers: Customer[];
  onEdit: (patch: Record<string, unknown>) => void;
}) {
  const [addingName, setAddingName] = useState(false);
  const [newName, setNewName] = useState(line.raw_name ?? "");

  return (
    <div
      className={`card transition border p-4 ${
        !line.include ? "opacity-40 border-slate-200 bg-slate-50" : "border-slate-200 bg-white shadow-sm"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={line.include}
            onChange={(e) => onEdit({ include: e.target.checked })}
            className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
          />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-extrabold text-slate-900">
                {line.raw_name ? `"${line.raw_name}"` : "(No name detected)"}
              </span>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  line.type === "credit"
                    ? "bg-red-100 text-red-700 border border-red-200"
                    : "bg-emerald-100 text-emerald-700 border border-emerald-200"
                }`}
              >
                {line.type === "credit" ? "Udhar (Credit)" : "Jama (Payment)"}
              </span>
              {line.transaction_id && (
                <span className="rounded-full bg-emerald-100 border border-emerald-300 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                  ✓ In Database
                </span>
              )}
              {line.duplicate && (
                <span className="rounded-full bg-amber-100 border border-amber-300 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                  ⚠️ Possible duplicate
                </span>
              )}
            </div>
            {line.raw_text && <p className="text-[11px] text-slate-500 mt-0.5">Original text: {line.raw_text}</p>}
          </div>
        </div>

        <div className="text-right">
          <div className="text-lg font-black text-slate-900">{inr(line.amount)}</div>
          <p className="text-[10px] font-medium text-slate-400">
            Confidence: {Math.round(line.confidence * 100)}%
          </p>
        </div>
      </div>

      {line.include && (
        <div className="mt-3 grid gap-2 border-t border-slate-100 pt-3 text-xs sm:grid-cols-2">
          <div>
            <label className="block text-[11px] font-bold text-slate-600 mb-1">
              Assign to Khata Customer:
            </label>
            {!addingName ? (
              <div className="flex gap-2">
                <select
                  value={line.customer_id ?? ""}
                  onChange={(e) => onEdit({ customer_id: e.target.value || null })}
                  className="input text-xs py-1.5"
                >
                  <option value="">-- Choose matching customer --</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} {c.landmark ? `(${c.landmark})` : ""}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => setAddingName(true)}
                  className="btn-ghost text-[11px] px-2 py-1 flex-shrink-0"
                  title="Create new customer for this name"
                >
                  + New
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="New customer name"
                  className="input text-xs py-1.5"
                />
                <button
                  type="button"
                  onClick={() => {
                    if (newName.trim()) {
                      onEdit({ create_customer_name: newName.trim() });
                      setAddingName(false);
                    }
                  }}
                  className="btn bg-emerald-600 text-white font-bold text-[11px] px-3 py-1"
                >
                  Create
                </button>
                <button
                  type="button"
                  onClick={() => setAddingName(false)}
                  className="btn-ghost text-[11px] px-2 py-1"
                >
                  ✕
                </button>
              </div>
            )}
          </div>

          <div>
            <label className="block text-[11px] font-bold text-slate-600 mb-1">
              Note / Items:
            </label>
            <input
              type="text"
              value={line.note ?? ""}
              onChange={(e) => onEdit({ note: e.target.value })}
              placeholder="e.g. 5kg sugar, 1L oil"
              className="input text-xs py-1.5"
            />
          </div>
        </div>
      )}
    </div>
  );
}
