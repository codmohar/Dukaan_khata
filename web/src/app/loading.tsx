export default function Loading() {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center p-6 text-center">
      <div className="relative flex h-20 w-20 items-center justify-center">
        <div className="absolute inset-0 rounded-full border-4 border-emerald-200" />
        <div className="absolute inset-0 animate-spin rounded-full border-4 border-transparent border-t-emerald-600" />
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-600 text-2xl font-black text-white shadow-lg shadow-emerald-600/30">
          D
        </div>
      </div>
      <h2 className="mt-5 text-lg font-extrabold text-slate-800 tracking-tight">
        DukaanAI Khata
      </h2>
      <p className="mt-1 text-xs font-medium text-slate-500 animate-pulse">
        Loading your shop ledger…
      </p>
    </div>
  );
}

